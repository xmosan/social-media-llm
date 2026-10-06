"""Calendar instants and local month boundaries; no production application import."""
import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from test_security import DatabaseCase
from app.models import Org, IGAccount, Post
from app.routes import app_pages


class CalendarTests(DatabaseCase):
    def setUp(self):
        super().setUp()
        for model in (IGAccount, Post):
            model.__table__.create(self.engine)
        self.db.add(Org(id=1, name="Fixture"))
        self.account = IGAccount(id=1, org_id=1, name="Fixture", username="fixture", ig_user_id="fixture", access_token="fake-test-token", active=True)
        self.db.add(self.account)
        self.db.commit()
        self.user = SimpleNamespace(active_org_id=1, is_superadmin=False)

    def render(self, tz):
        class FixedClock(datetime):
            @classmethod
            def now(cls, zone=None):
                return datetime(2026, 10, 6, 23, tzinfo=timezone.utc).astimezone(zone)
        with patch.object(app_pages, "datetime", FixedClock), \
             patch.object(app_pages, "get_active_context", return_value=(self.account, [self.account], True)), \
             patch.object(app_pages, "render_app_page", side_effect=lambda **kwargs: kwargs["content"]):
            return asyncio.run(app_pages.app_calendar_page(user=self.user, db=self.db, tz=tz))

    def test_calendar_and_agenda_show_the_same_local_scheduled_time(self):
        self.db.add(Post(id=1, org_id=1, ig_account_id=1, status="scheduled", caption="Scheduled fixture",
                         scheduled_time=datetime(2026, 10, 7, 13, tzinfo=timezone.utc)))
        self.db.commit()
        rendered = self.render("America/Detroit")
        self.assertIn("9:00 am", rendered)
        self.assertIn("Oct 7, 9:00 AM", rendered)
        self.assertIn("Times shown in America/Detroit", rendered)
        self.assertIn("1:00 pm", self.render("UTC"))

    def test_previous_local_month_does_not_leak_into_this_month(self):
        self.db.add(Post(id=1, org_id=1, ig_account_id=1, status="scheduled", caption="Previous local month",
                         scheduled_time=datetime(2026, 10, 1, 2, tzinfo=timezone.utc)))
        self.db.commit()
        self.assertNotIn("Previous local month", self.render("America/Detroit"))
        self.assertIn("Previous local month", self.render("UTC"))

    def test_day_rollover_dst_and_published_date_use_correct_instants(self):
        post = SimpleNamespace(status="scheduled", scheduled_time=datetime(2026, 10, 7, 2, tzinfo=timezone.utc), published_time=None)
        tz = ZoneInfo("America/Detroit")
        value = app_pages._calendar_post_time(post, tz)
        self.assertEqual((value.day, value.hour), (6, 22))
        post.scheduled_time = datetime(2026, 11, 2, 14)  # Legacy naive UTC row, after DST.
        self.assertEqual(app_pages._calendar_post_time(post, tz).hour, 9)
        post.status = "published"
        post.published_time = datetime(2026, 10, 6, 23, tzinfo=timezone.utc)
        value = app_pages._calendar_post_time(post, tz)
        self.assertEqual((value.month, value.day, value.hour), (10, 6, 19))

    def test_invalid_timezone_is_rejected(self):
        with self.assertRaises(HTTPException) as result:
            self.render("not/a-timezone")
        self.assertEqual(result.exception.status_code, 422)

    def test_calendar_passes_published_state_to_the_viewer(self):
        self.db.add(Post(id=1, org_id=1, ig_account_id=1, status="published", caption="Published fixture",
                         published_time=datetime(2026, 10, 6, 23, tzinfo=timezone.utc)))
        self.db.commit()
        self.assertIn("'', &quot;published&quot;)", self.render("America/Detroit"))

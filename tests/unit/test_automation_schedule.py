"""Cadence and durable rotation checks without starting a scheduler."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from test_security import DatabaseCase
from test_ownership import load_scheduler
from test_source_integrity import load_isolated_service
from app.models import IGAccount, Org, Post, TopicAutomation, StyleDNA
from app.services.automation_schedule import automation_triggers, next_automation_time
from app.services.rotation_engine import pick_topic, record_topic_used


class CadenceTests(unittest.TestCase):
    account = SimpleNamespace(timezone="America/Detroit", daily_post_time="09:00")

    def auto(self, **changes):
        return SimpleNamespace(**{**dict(frequency="daily", custom_days=[], post_time_local="09:00", timezone="America/Detroit", posts_per_day=1, post_spacing_hours=4), **changes})

    def test_weekly_and_custom_follow_selected_weekdays(self):
        tuesday = datetime(2026, 10, 6, 14, tzinfo=timezone.utc)
        self.assertEqual(next_automation_time(self.account, self.auto(frequency="weekly"), tuesday), datetime(2026, 10, 9, 13, tzinfo=timezone.utc))
        self.assertEqual(next_automation_time(self.account, self.auto(frequency="3x_weekly"), tuesday), datetime(2026, 10, 7, 13, tzinfo=timezone.utc))
        self.assertEqual(next_automation_time(self.account, self.auto(frequency="custom", custom_days=["Mon"]), tuesday), datetime(2026, 10, 12, 13, tzinfo=timezone.utc))

    def test_multiple_slots_and_midnight_keep_base_day_cadence(self):
        monday = datetime(2026, 10, 5, 14, tzinfo=timezone.utc)
        self.assertEqual(next_automation_time(self.account, self.auto(posts_per_day=2), monday), datetime(2026, 10, 5, 17, tzinfo=timezone.utc))
        auto = self.auto(frequency="custom", custom_days=["Mon"], post_time_local="22:00", posts_per_day=2)
        triggers = automation_triggers(self.account, auto)
        self.assertEqual(triggers[1].get_next_fire_time(None, monday).astimezone(timezone.utc), datetime(2026, 10, 6, 6, tzinfo=timezone.utc))

    def test_regular_morning_keeps_local_time_across_dst_change(self):
        now = datetime(2026, 10, 31, 14, tzinfo=timezone.utc)
        self.assertEqual(next_automation_time(self.account, self.auto(), now), datetime(2026, 11, 1, 14, tzinfo=timezone.utc))

    def test_invalid_schedules_do_not_fall_back_to_daily(self):
        for changes in ({"frequency": "bad"}, {"frequency": "custom"}, {"frequency": "custom", "custom_days": ["bad"]},
                        {"post_time_local": "25:00"}, {"timezone": "Not/AZone"}, {"posts_per_day": 0}, {"posts_per_day": 7}, {"post_spacing_hours": 0}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                automation_triggers(self.account, self.auto(**changes))


class RotationPersistenceTests(DatabaseCase):
    def setUp(self):
        super().setUp()
        for model in (IGAccount, Post, TopicAutomation, StyleDNA):
            model.__table__.create(self.engine)
        self.db.add(Org(id=1, name="Fixture"))
        self.account = IGAccount(id=1, org_id=1, name="Fixture", active=True, ig_user_id="fixture", access_token="fake-token", timezone="UTC")
        self.auto = TopicAutomation(id=1, org_id=1, ig_account_id=1, name="Fixture", topic_prompt="Fixture", enabled=True,
                                    frequency="custom", custom_days=["Wed"], post_time_local="10:00", timezone="UTC")
        self.db.add_all([self.account, self.auto])
        self.db.commit()

    def test_scheduler_registers_same_weekday_trigger(self):
        scheduler = load_scheduler()
        instance = Mock()
        instance.get_jobs.return_value = []
        scheduler.sync_automation_jobs(instance, lambda: self.db)
        trigger = instance.add_job.call_args.kwargs["trigger"]
        now = datetime(2026, 10, 6, 12, tzinfo=timezone.utc)
        self.assertEqual(trigger.get_next_fire_time(None, now), next_automation_time(self.account, self.auto, now))

    def test_history_survives_session_and_exhaustion_uses_oldest(self):
        for id_, topic, age in [(1, "wisdom", 1), (2, "patience", 2)]:
            post = Post(id=id_, org_id=1, ig_account_id=1, automation_id=1, caption="Fixture")
            record_topic_used(post, topic, None)
            post.flags = {**post.flags, "rotation_used_at": (datetime.now(timezone.utc) - timedelta(days=age)).isoformat()}
            self.db.add(post)
        self.db.commit()
        self.db.close()
        self.assertEqual(pick_topic(["wisdom", "patience", "gratitude"], 1, self.db), "gratitude")
        self.assertEqual(pick_topic(["wisdom", "patience"], 1, self.db), "patience")

    def test_style_selection_reads_saved_history_and_returns_selected_id(self):
        for id_ in (1, 2):
            self.db.add(StyleDNA(id=id_, org_id=1, name="Fixture", family="sacred_black", atmosphere="calm", ornament_level="none", tone_style="deep", variation_pool=[], locked_traits={}))
        post = Post(org_id=1, ig_account_id=1, automation_id=1)
        record_topic_used(post, "wisdom", 1)
        self.db.add(post)
        self.auto.automation_version = 2
        self.auto.style_dna_pool = [1, 2]
        self.db.commit()
        service = load_isolated_service("automation_service")
        selected = service.get_automation_style_dna(self.db, self.auto)
        self.assertEqual(selected.style_id, 2)

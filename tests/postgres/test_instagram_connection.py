"""Real PostgreSQL OAuth replay, selection atomicity and additive migration checks."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import asyncio
import threading
import unittest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.db import engine
from app.models import Base, Org, User, OrgMember, IGAccount, Post, TopicAutomation, ContentProfile, InstagramConnectionAttempt as Attempt
from app.services import instagram_connection as connection
from app.routes.ig_accounts import SelectionPayload
from scripts.migrate_instagram_connections import migrate


class InstagramPostgresChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert engine.url.database=='sabeel_test' and engine.url.query.get('host','').startswith('/tmp/sabeel-pg-test-')
        Base.metadata.create_all(engine)

    def setUp(self):
        with engine.begin() as c:
            c.execute(text('TRUNCATE '+', '.join('"'+t.name+'"' for t in Base.metadata.sorted_tables)+' RESTART IDENTITY CASCADE'))
        with Session(engine) as db:
            db.add(Org(id=1,name='Synthetic workspace'));db.flush()
            db.add(User(id=1,email='synthetic@fixture.test',name='Synthetic',active_org_id=1));db.commit()
        self.request=SimpleNamespace(session={},headers={'origin':'https://app.sabeelstudio.com'})

    def ready(self):
        with Session(engine) as db:
            state=connection.begin(db,self.request,1,1)
            id_=connection.claim_callback(db,self.request,1,1,state)
            connection.finish_discovery(db,id_,[{'ig_user_id':'111','fb_page_id':'222','username':'fixture','name':'Fixture','profile_picture_url':None}],{'access_token':'synthetic-token','expires_at':None})
        return id_

    def test_migration_from_absence_and_repeat_preserves_existing_workspace(self):
        with engine.begin() as c:
            c.execute(text('DROP TABLE instagram_connection_attempts'))
            migrate(c);migrate(c)
        self.ready()
        with Session(engine) as db:
            self.assertEqual(db.get(Org,1).name,'Synthetic workspace');self.assertEqual(db.query(Attempt).count(),1)

    def test_two_callbacks_claim_one_state_once(self):
        with Session(engine) as db:state=connection.begin(db,self.request,1,1)
        barrier=threading.Barrier(2)
        def attempt(_):
            with Session(engine) as db:
                barrier.wait(timeout=10)
                try:connection.claim_callback(db,self.request,1,1,state);return 200
                except HTTPException as e:return e.status_code
        with ThreadPoolExecutor(2) as pool:results=list(pool.map(attempt,range(2)))
        self.assertEqual(sorted(results),[200,400])

    def test_two_selections_commit_one_connection_once(self):
        self.ready();barrier=threading.Barrier(2)
        def attempt(_):
            request=SimpleNamespace(session=dict(self.request.session),headers=self.request.headers)
            with Session(engine) as db:
                user=db.get(User,1);barrier.wait(timeout=10)
                try:
                    connection.connect_selected(db,request,user,1,[SelectionPayload(ig_user_id='111',page_id='222')]);return 200
                except HTTPException as e:return e.status_code
        with ThreadPoolExecutor(2) as pool:results=list(pool.map(attempt,range(2)))
        self.assertEqual(sorted(results),[200,401])
        with Session(engine) as db:
            self.assertEqual(db.query(IGAccount).count(),1);self.assertEqual(db.query(Attempt).count(),0)
            self.assertTrue(db.get(User,1).has_connected_instagram)

    def test_bad_selection_rolls_back_and_retains_recoverable_handoff(self):
        self.ready()
        with Session(engine) as db:
            user=db.get(User,1)
            with self.assertRaises(HTTPException):connection.connect_selected(db,self.request,user,1,[SelectionPayload(ig_user_id='111',page_id='wrong')])
            self.assertEqual(db.query(IGAccount).count(),0);self.assertEqual(db.query(Attempt).count(),1)
            ids=connection.connect_selected(db,self.request,user,1,[SelectionPayload(ig_user_id='111',page_id='222')])
            self.assertEqual(len(ids),1);self.assertIsNone(db.get(IGAccount,ids[0]).expires_at)

    def test_expired_handoffs_are_purged_without_affecting_live_attempts(self):
        self.ready()
        with Session(engine) as db:
            db.add(Attempt(id='e'*64,user_id=1,org_id=1,state_hash='s'*64,stage='ready',encrypted_payload='expired',expires_at=datetime.now(timezone.utc)-timedelta(seconds=1)));db.commit()
        connection.purge_expired(lambda: Session(engine))
        with Session(engine) as db:self.assertEqual(db.query(Attempt).count(),1)

    def test_disconnect_preserves_post_foreign_key_and_content(self):
        from app.routes.auth_ig import instagram_disconnect
        self.ready()
        with Session(engine) as db:
            user=db.get(User,1)
            ids=connection.connect_selected(db,self.request,user,1,[SelectionPayload(ig_user_id='111',page_id='222')])
            post=Post(org_id=1,ig_account_id=ids[0],status='draft',caption='Synthetic saved caption',source_text='Synthetic source fixture')
            db.add(post);db.commit();post_id=post.id
            asyncio.run(instagram_disconnect(self.request,db,user,1))
            db.expire_all();post=db.get(Post,post_id)
            self.assertEqual(post.ig_account_id,ids[0]);self.assertEqual(post.caption,'Synthetic saved caption')
            self.assertFalse(db.get(IGAccount,ids[0]).active)
            from app.routes.app_pages import get_active_context
            account,_,connected=get_active_context(db,user,1)
            self.assertEqual(account.id,post.ig_account_id);self.assertFalse(connected)
            db.commit();db.expire_all();self.assertFalse(db.get(IGAccount,ids[0]).active)

    def test_legacy_finalizer_without_account_does_not_make_broken_automation(self):
        from app.routes.app_pages import finalize_onboarding, OnboardingFinalize
        payload=OnboardingFinalize(orgName='Fixture',contentMode='quran',autoTopic='Fixture topic',autoTime='09:00')
        with Session(engine) as db:
            asyncio.run(finalize_onboarding(payload,db.get(User,1),db,1))
            self.assertEqual(db.query(TopicAutomation).count(),0)
            self.assertTrue(db.get(User,1).onboarding_complete)
            self.assertEqual(db.query(ContentProfile).count(),1)
        self.ready()
        with Session(engine) as db:
            user=db.get(User,1)
            connection.connect_selected(db,self.request,user,1,[SelectionPayload(ig_user_id='111',page_id='222')])
            asyncio.run(finalize_onboarding(payload,user,db,1))
            self.assertFalse(db.query(TopicAutomation).one().enabled)
            self.assertEqual(db.query(TopicAutomation).one().approval_mode,'needs_manual_approve')

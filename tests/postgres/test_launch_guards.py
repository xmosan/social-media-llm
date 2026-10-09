"""Atomic limits, migration and provider boundaries against disposable PostgreSQL."""
import importlib.util
from contextlib import ExitStack
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
import threading
import unittest
from unittest.mock import patch, Mock
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.db import engine
from app.models import Base, Org, Post, User, UsageBucket, AIUsageLease
from app.config import settings
from app.security.usage_context import workspace_usage
from app.services import usage_limits as limits, image_provider, text_provider

ROOT=Path(__file__).resolve().parents[2]


class LaunchPostgresChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert engine.url.database=='sabeel_test' and engine.url.query.get('host','').startswith('/tmp/sabeel-pg-test-')
        Base.metadata.create_all(engine)

    def setUp(self):
        with engine.begin() as conn:
            names=', '.join('"'+table.name+'"' for table in Base.metadata.sorted_tables)
            conn.execute(text('TRUNCATE '+names+' RESTART IDENTITY CASCADE'))
        with Session(engine) as db:
            db.add_all([Org(id=1,name='Fixture workspace'),Org(id=2,name='Second workspace')]);db.commit()

    def count(self,kind='image',org=1):
        return limits.usage_status(org)['images' if kind=='image' else 'text']['used']

    def overrides(self,**kwargs):
        stack=ExitStack()
        for name,value in kwargs.items():stack.enter_context(patch.object(settings,name,value))
        return stack

    def test_migration_can_repeat_and_preserves_current_users_posts_and_counters(self):
        spec=importlib.util.spec_from_file_location('launch_migration',ROOT/'scripts/migrate_launch_guards.py')
        migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
        with workspace_usage(1),limits.paid_call('image'):pass
        with engine.begin() as conn:migration.migrate(conn);migration.migrate(conn)
        self.assertEqual(self.count(),1)
        with Session(engine) as db:self.assertEqual(db.get(Org,1).name,'Fixture workspace')
        # Also exercise migration from absence on this disposable database only.
        with engine.begin() as conn:
            conn.execute(text('DROP TABLE ai_usage_leases'));conn.execute(text('DROP TABLE usage_buckets'))
            migration.migrate(conn);migration.migrate(conn)
        with workspace_usage(1),limits.paid_call('text'):pass
        self.assertEqual(self.count('text'),1)

    def test_concurrent_daily_reservations_cannot_exceed_workspace_limit(self):
        barrier=threading.Barrier(12)
        def attempt(_):
            barrier.wait(timeout=10)
            try:
                with workspace_usage(1),limits.paid_call('image'):pass
                return 200
            except limits.UsageLimitError as error:return error.status_code
        with self.overrides(ai_workspace_daily_images=3,ai_global_daily_images=50,ai_workspace_concurrency=10,ai_global_concurrency=50):
            with ThreadPoolExecutor(12) as pool:results=list(pool.map(attempt,range(12)))
        self.assertEqual(results.count(200),3);self.assertEqual(results.count(429),9)
        self.assertEqual(self.count(),3)
        with Session(engine) as db:self.assertEqual(db.query(AIUsageLease).count(),0)

    def test_concurrency_denial_spends_nothing_and_crashed_lease_expires(self):
        with self.overrides(ai_workspace_concurrency=1),workspace_usage(1):
            lease=limits.reserve('image')
            with self.assertRaises(limits.UsageLimitError):limits.reserve('text')
            self.assertEqual(self.count('text'),0)
            with engine.begin() as conn:
                conn.execute(text("UPDATE ai_usage_leases SET expires_at=clock_timestamp()-interval '1 second' WHERE id=:id"),{'id':lease})
            with limits.paid_call('text'):pass
        self.assertEqual(self.count(),1);self.assertEqual(self.count('text'),1)
        with Session(engine) as db:self.assertEqual(db.query(AIUsageLease).count(),0)

    def test_global_limit_covers_other_workspaces_and_does_not_charge_rejections(self):
        with self.overrides(ai_global_daily_images=1):
            with workspace_usage(1),limits.paid_call('image'):pass
            with workspace_usage(2),self.assertRaises(limits.UsageLimitError) as caught:limits.reserve('image')
        self.assertEqual(caught.exception.status_code,429);self.assertEqual(self.count(org=2),0)
        self.assertGreater(int(caught.exception.headers['Retry-After']),0)

    def test_global_concurrency_prevents_parallel_other_workspace(self):
        with self.overrides(ai_global_concurrency=1),workspace_usage(1),limits.paid_call('image'):
            with workspace_usage(2),self.assertRaises(limits.UsageLimitError):limits.reserve('image')
        self.assertEqual(self.count(org=2),0)

    def test_failed_and_fallback_provider_attempts_count_and_release_slots(self):
        image=SimpleNamespace(provider='openai',model='fixture',image=None)
        with workspace_usage(1),patch.object(settings,'openai_api_key','fixture'),patch.object(image_provider,'generate_openai_image',side_effect=[image_provider.ImageGenerationError('unavailable',404),image]) as provider:
            self.assertIs(image_provider.generate_configured_image('Synthetic fixture'),image)
            self.assertEqual(provider.call_count,2)
        self.assertEqual(self.count(),2)
        with workspace_usage(1),patch.object(settings,'openai_api_key','fixture'),patch.object(text_provider,'request_text',side_effect=text_provider.TextGenerationError('timeout')):
            with self.assertRaises(text_provider.TextGenerationError):text_provider.generate_text('Synthetic fixture')
        self.assertEqual(self.count('text'),1)
        with Session(engine) as db:self.assertEqual(db.query(AIUsageLease).count(),0)

    def test_counter_commit_survives_unrelated_draft_rollback_and_daily_window_reset(self):
        with Session(engine) as draft:
            draft.get(Org,1).name='Uncommitted draft transaction'
            with workspace_usage(1),limits.paid_call('image'):pass
            draft.rollback()
        self.assertEqual(self.count(),1)
        with engine.begin() as conn:
            conn.execute(text("UPDATE usage_buckets SET window_start=window_start-interval '1 day'"))
        self.assertEqual(self.count(),0)
        with workspace_usage(1),limits.paid_call('image'):pass
        self.assertEqual(self.count(),1)

    def test_auth_throttle_has_normalized_private_keys_and_bounded_parallel_attempts(self):
        barrier=threading.Barrier(8)
        def attempt(i):
            barrier.wait(timeout=10)
            try:limits.check_auth_attempt(' CREATOR@example.com ' if i%2 else 'creator@EXAMPLE.com');return 200
            except limits.UsageLimitError as error:return error.status_code
        with self.overrides(auth_identity_attempts=3):
            with ThreadPoolExecutor(8) as pool:results=list(pool.map(attempt,range(8)))
        self.assertEqual(results.count(200),3);self.assertEqual(results.count(429),5)
        with Session(engine) as db:
            buckets=db.query(UsageBucket).all()
            self.assertEqual(len(buckets),2)
            for bucket in buckets:self.assertNotIn('creator',bucket.key);self.assertNotIn('@',bucket.key)

    def test_closed_signup_and_real_login_throttle_do_not_issue_tokens_on_denial(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.routes import auth
        from app.db import get_db
        from app.security.auth import get_password_hash
        with Session(engine) as db:
            db.add(User(email='creator@example.com',name='Fixture',is_active=True,password_hash=get_password_hash('isolated-password'),active_org_id=1));db.commit()
        def dependency():
            with Session(engine) as db:yield db
        app=FastAPI();app.include_router(auth.router);app.dependency_overrides[get_db]=dependency
        with TestClient(app,base_url='https://testserver') as client,self.overrides(signup_enabled=False,auth_identity_attempts=2):
            response=client.post('/auth/register',json={'email':'new@example.com','name':'Fixture','password':'long-disposable-password'})
            self.assertEqual(response.status_code,403)
            self.assertEqual(client.post('/auth/login',data={'username':'creator@example.com','password':'wrong'}).status_code,401)
            self.assertEqual(client.post('/auth/login',data={'username':'CREATOR@example.com','password':'isolated-password'}).status_code,200)
            response=client.post('/auth/login',data={'username':'creator@example.com','password':'isolated-password'})
            self.assertEqual(response.status_code,429);self.assertIn('Retry-After',response.headers);self.assertNotIn('set-cookie',response.headers)

    def test_paid_success_is_not_lost_if_slot_cleanup_fails(self):
        from sqlalchemy.exc import OperationalError
        original=limits._session
        with workspace_usage(1),patch.object(limits,'_session',side_effect=[original(),OperationalError('sql',{},Exception('fixture'))]):
            with limits.paid_call('image'):result='good existing image'
        self.assertEqual(result,'good existing image');self.assertEqual(self.count(),1)
        with Session(engine) as db:self.assertEqual(db.query(AIUsageLease).count(),1)

    def test_http_writing_flow_uses_authorized_workspace_and_returns_429_without_dispatch(self):
        import importlib.util, sys
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.db import get_db
        from app.models import OrgMember
        from app.security.auth import create_access_token
        from app.security.usage_context import UsageContextMiddleware
        from app.routes import app_pages, studio
        from app.services import llm
        spec=importlib.util.spec_from_file_location('launch_real_llm',ROOT/'app/services/llm.py')
        real=importlib.util.module_from_spec(spec);spec.loader.exec_module(real)
        with Session(engine) as db:
            db.add(User(id=1,email='fixture@example.com',is_active=True,active_org_id=1))
            db.add(OrgMember(org_id=1,user_id=1));db.commit()
        def dependency():
            with Session(engine) as db:yield db
        app=FastAPI();app.add_middleware(UsageContextMiddleware)
        app.include_router(app_pages.router);app.include_router(studio.router)
        app.dependency_overrides[get_db]=dependency
        result=SimpleNamespace(status='completed',output=[],output_text='Separate fixture social copy.',model='fixture',usage=SimpleNamespace(output_tokens=5))
        with self.overrides(ai_workspace_daily_text=1,openai_api_key='fixture'),patch.object(llm,'refine_caption',real.refine_caption,create=True),patch.object(text_provider,'OpenAI') as provider,TestClient(app,base_url='https://testserver') as client:
            provider.return_value.__enter__.return_value.responses.create.return_value=result
            headers={'Authorization':'Bearer '+create_access_token({'sub':'1'})}
            self.assertEqual(client.post('/api/ai/refine',headers=headers,json={'text':'Synthetic caption','type':'clarity'}).status_code,200)
            response=client.post('/api/ai/refine',headers=headers,json={'text':'Synthetic caption','type':'clarity'})
            self.assertEqual(response.status_code,429);self.assertIn('Retry-After',response.headers)
            provider.return_value.__enter__.return_value.responses.create.assert_called_once()
            usage=client.get('/api/studio/usage',headers=headers).json()
            self.assertEqual(usage['text'],{'used':1,'limit':1})
            self.assertEqual(client.get('/api/studio/usage',headers=headers|{'X-Org-Id':'2'}).status_code,403)

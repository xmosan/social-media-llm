"""Tester access with real disposable PostgreSQL; no production users or providers."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
import threading
import unittest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.db import engine, get_db
from app.config import settings
from app.models import Base, User, Org, OrgMember, TesterInvitation, ApiKey, IGAccount, Post, TopicAutomation, UsageBucket
from app.routes import auth, tester_access
from app.security.auth import create_access_token, get_password_hash, create_user_access_token
from app.security.ownership import require_account
from app.security.rbac import get_current_org_id
from app.security.usage_context import workspace_usage
from app.services import tester_invitations as service, usage_limits
from scripts.migrate_tester_access import migrate
from scripts.migrate_session_version import migrate as migrate_sessions
from app.services.creator_access import legacy_access_plan, retire_legacy_access

ORIGIN = 'https://app.sabeelstudio.com'
PASSWORD = 'synthetic-pilot-password-only'


class TesterAccessChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert engine.url.database == 'sabeel_test' and engine.url.query.get('host', '').startswith('/tmp/sabeel-pg-test-')
        Base.metadata.create_all(engine)

    def setUp(self):
        owner = patch.object(settings, "platform_owner_email", "admin@fixture.test")
        owner.start(); self.addCleanup(owner.stop)
        with engine.begin() as c:
            c.execute(text('TRUNCATE ' + ', '.join('"'+t.name+'"' for t in Base.metadata.sorted_tables) + ' RESTART IDENTITY CASCADE'))
        self.db = Session(engine, expire_on_commit=False); self.addCleanup(self.db.close)
        self.db.add(Org(name='Existing private workspace')); self.db.flush()
        self.db.add(User(email='admin@fixture.test', name='Admin', is_superadmin=True, active_org_id=1)); self.db.commit()
        app = FastAPI(); app.include_router(tester_access.router); app.include_router(auth.router)
        app.dependency_overrides[get_db] = lambda: self.db
        @app.get('/scope')
        def scope(org=Depends(get_current_org_id)):
            return {'org': org}
        self.client = TestClient(app, base_url=ORIGIN); self.addCleanup(self.client.close)
        self.admin = {'Authorization': 'Bearer ' + create_access_token({'sub':'1'}), 'Origin': ORIGIN}
        self.payload = {'email':'creator@fixture.test','name':'Fixture Creator','password':PASSWORD}

    def issue(self):
        row, token = service.issue(self.db, email=self.payload['email'], admin_id=1)
        return row.id, token

    def join(self):
        invitation_id, token = self.issue()
        response = self.client.post('/auth/tester-invitations/redeem', json=dict(self.payload, token=token), headers={'Origin':ORIGIN})
        self.assertEqual(response.status_code, 200, response.text)
        return invitation_id, self.db.query(User).filter_by(email=self.payload['email']).one(), response

    def fixture_work(self, user):
        account = IGAccount(org_id=user.active_org_id, name='Fixture', ig_user_id='123', access_token='synthetic-only')
        self.db.add(account); self.db.flush()
        auto = TopicAutomation(org_id=user.active_org_id, ig_account_id=account.id, name='Fixture plan', topic_prompt='Synthetic', enabled=True)
        self.db.add(auto)
        for state in ('scheduled','published','publish_unknown','publishing'):
            self.db.add(Post(org_id=user.active_org_id, ig_account_id=account.id, status=state, caption='Keep exact draft', scheduled_time=datetime.now(timezone.utc)))
        self.db.commit()
        return account

    def legacy_creator(self, email='returning@fixture.test', password='old7'):
        org = Org(name='Retained legacy workspace'); self.db.add(org); self.db.flush()
        user = User(email=email, name='Keep original name', password_hash=get_password_hash(password), active_org_id=org.id)
        self.db.add(user); self.db.flush()
        self.db.add(OrgMember(org_id=org.id, user_id=user.id, role='owner')); self.db.commit()
        return user

    def retire(self):
        plan = legacy_access_plan(self.db, 'admin@fixture.test')
        retire_legacy_access(self.db, owner_email='admin@fixture.test', expected_user_ids=plan['user_ids'])
        self.db.commit(); return plan

    def test_legacy_retirement_protects_owner_invited_pilot_and_saved_work(self):
        _, pilot, _ = self.join(); self.client.cookies.clear()
        legacy = self.legacy_creator(); account = self.fixture_work(legacy)
        self.db.add(OrgMember(org_id=1,user_id=1,role='owner'))
        self.db.add(OrgMember(org_id=1,user_id=legacy.id,role='member'))
        self.db.add(ApiKey(org_id=1,name='Shared old key',key_hash='fixture-shared-key'))
        self.db.commit()
        owner_before = self.db.get(User,1).session_version
        plan = self.retire()
        self.assertEqual(plan['user_ids'],[legacy.id]);self.assertNotIn(1,plan['workspace_ids'])
        self.db.refresh(legacy);self.assertFalse(legacy.is_active);self.assertEqual(legacy.session_version,1)
        self.assertTrue(self.db.get(User,1).is_active);self.assertEqual(self.db.get(User,1).session_version,owner_before)
        self.assertTrue(self.db.get(User,pilot.id).is_active)
        self.assertIsNone(self.db.get(Org,1).tester_revoked_at)
        self.assertIsNone(self.db.get(Org,pilot.active_org_id).tester_revoked_at)
        self.assertIsNotNone(self.db.query(ApiKey).one().revoked_at)
        self.assertEqual({p.status for p in self.db.query(Post).all()},{'drafted','published','publish_unknown','publishing'})
        self.assertTrue(all(p.caption=='Keep exact draft' for p in self.db.query(Post).all()))
        self.assertFalse(self.db.query(TopicAutomation).one().enabled)
        with self.assertRaises(HTTPException):require_account(self.db,legacy.active_org_id,account.id)
        self.retire();self.db.refresh(legacy);self.assertEqual(legacy.session_version,1)

    def test_retirement_requires_exact_preview_and_matching_owner(self):
        user=self.legacy_creator()
        for owner,ids in [('admin@fixture.test',[]),('wrong@fixture.test',[user.id])]:
            with self.assertRaises(HTTPException):retire_legacy_access(self.db,owner_email=owner,expected_user_ids=ids)
        self.db.refresh(user);self.assertTrue(user.is_active);self.assertEqual(user.session_version,0)

    def test_returning_link_restores_same_workspace_without_password_reset_or_old_sessions(self):
        user=self.legacy_creator();self.fixture_work(user)
        old_token=create_access_token({'sub':str(user.id)});old_hash=user.password_hash
        self.retire()
        row,token=service.issue(self.db,email=user.email,admin_id=1,returning=True)
        self.assertEqual(self.client.post('/auth/login',data={'username':user.email,'password':'old7'}).status_code,401)
        check=self.client.post('/auth/tester-invitations/check',json={'token':token},headers={'Origin':ORIGIN})
        self.assertTrue(check.json()['returning']);self.assertNotIn(user.email,check.text)
        for email,password,code in [(user.email,'wrong',401),('wrong@fixture.test','old7',422)]:
            r=self.client.post('/auth/tester-invitations/return',json={'token':token,'email':email,'password':password},headers={'Origin':ORIGIN})
            self.assertEqual(r.status_code,code);self.assertNotIn(token,r.text)
        self.db.refresh(row);self.assertIsNone(row.redeemed_at)
        r=self.client.post('/auth/tester-invitations/return',json={'token':token,'email':user.email,'password':'old7'},headers={'Origin':ORIGIN})
        self.assertEqual(r.status_code,200,r.text)
        self.db.refresh(user);self.assertEqual(user.password_hash,old_hash);self.assertEqual(user.name,'Keep original name')
        self.assertEqual(user.session_version,2);self.assertFalse(user.is_superadmin)
        self.assertEqual(self.db.query(User).count(),2);self.assertEqual(self.db.query(Org).count(),2)
        self.assertEqual(self.client.get('/scope').json(),{'org':user.active_org_id})
        self.assertEqual(self.client.get('/scope',headers={'X-Org-Id':'1'}).status_code,403)
        self.assertFalse(self.db.query(TopicAutomation).one().enabled)
        self.assertFalse(self.db.query(Post).filter_by(status='scheduled').count())
        self.client.cookies.clear()
        self.assertEqual(self.client.get('/auth/me',headers={'Authorization':'Bearer '+old_token}).status_code,401)
        self.assertEqual(self.client.post('/auth/login',data={'username':user.email,'password':'old7'}).status_code,200)
        self.assertEqual(self.client.get('/scope').status_code,200)

    def test_returning_invitation_requires_explicit_disabled_private_creator(self):
        user=self.legacy_creator()
        with self.assertRaises(HTTPException):service.issue(self.db,email=user.email,admin_id=1,returning=True)
        self.retire()
        with self.assertRaises(HTTPException):service.issue(self.db,email=user.email,admin_id=1)
        with self.assertRaises(HTTPException):service.issue(self.db,email='admin@fixture.test',admin_id=1,returning=True)
        self.db.add(OrgMember(org_id=user.active_org_id,user_id=1,role='member'));self.db.commit()
        with self.assertRaises(HTTPException):service.issue(self.db,email=user.email,admin_id=1,returning=True)

    def test_returning_invitation_revoke_replace_and_wrong_endpoint_preserve_account(self):
        user=self.legacy_creator();self.retire()
        row,token=service.issue(self.db,email=user.email,admin_id=1,returning=True)
        with self.assertRaises(HTTPException):service.redeem(self.db,token=token,email=user.email,name='Overwrite',password=PASSWORD)
        service.revoke(self.db,row.id,1);self.db.refresh(user)
        self.assertFalse(user.is_active);self.assertEqual(user.session_version,1)
        row,new_token=service.issue(self.db,email=user.email,admin_id=1,returning=True)
        with self.assertRaises(HTTPException):service.pending(self.db,token)
        self.assertEqual(service.pending(self.db,new_token).id,row.id)

    def test_returning_redemption_rechecks_membership_and_rolls_back_failure(self):
        user=self.legacy_creator();self.retire()
        row,token=service.issue(self.db,email=user.email,admin_id=1,returning=True)
        with patch.object(self.db,'commit',side_effect=RuntimeError('Synthetic failure')),self.assertRaises(RuntimeError):
            service.restore(self.db,token=token,email=user.email,password='old7')
        self.db.refresh(user);self.db.refresh(row)
        self.assertFalse(user.is_active);self.assertIsNone(row.redeemed_at);self.assertEqual(user.session_version,1)
        self.db.add(OrgMember(org_id=user.active_org_id,user_id=1,role='member'));self.db.commit()
        with self.assertRaises(HTTPException):service.restore(self.db,token=token,email=user.email,password='old7')
        self.db.refresh(user);self.assertFalse(user.is_active)

    def test_returning_redemption_is_single_use_under_concurrency(self):
        user=self.legacy_creator();self.retire()
        row,token=service.issue(self.db,email=user.email,admin_id=1,returning=True)
        email=user.email;barrier=threading.Barrier(2)
        def attempt(_):
            with Session(engine) as db:
                barrier.wait(timeout=10)
                try:service.restore(db,token=token,email=email,password='old7');return 200
                except HTTPException as error:return error.status_code
        with ThreadPoolExecutor(2) as pool:results=list(pool.map(attempt,range(2)))
        self.assertEqual(sorted(results),[200,410]);self.assertEqual(self.db.query(User).count(),2)

    def test_session_migration_is_additive_repeatable_and_retains_current_sessions(self):
        with engine.begin() as c:
            c.execute(text('ALTER TABLE users DROP COLUMN session_version'))
            migrate_sessions(c);migrate_sessions(c)
        self.db.expire_all();self.assertEqual(self.db.get(User,1).session_version,0)
        self.assertEqual(self.client.get('/auth/me',headers=self.admin).status_code,200)

    def test_closed_public_signup_still_allows_one_private_workspace_and_normal_login(self):
        self.payload['password'] = 'Test123!'
        with patch.object(settings, 'signup_enabled', False):
            self.assertEqual(self.client.post('/auth/register', json=self.payload).status_code, 403)
            invitation_id, user, response = self.join()
        self.assertFalse(user.is_superadmin); self.assertTrue(user.is_active)
        self.assertNotEqual(user.active_org_id, 1)
        membership = self.db.query(OrgMember).filter_by(user_id=user.id).one()
        self.assertEqual((membership.role, membership.org_id), ('owner', user.active_org_id))
        self.assertEqual(self.db.get(Org, user.active_org_id).tester_expires_at, user.tester_expires_at)
        for flag in ('HttpOnly','Secure','SameSite=lax'): self.assertIn(flag, response.headers['set-cookie'])
        self.assertEqual(self.client.get('/scope').json(), {'org':user.active_org_id})
        self.assertEqual(self.client.get('/scope', headers={'X-Org-Id':'1'}).status_code, 403)
        self.assertEqual(self.client.get('/api/admin/tester-invitations').status_code, 403)
        self.client.post('/auth/logout')
        login = self.client.post('/auth/login', data={'username':'CREATOR@fixture.test','password':self.payload['password']})
        self.assertEqual(login.status_code, 200)

    def test_eight_arabic_characters_can_join_and_sign_in(self):
        self.payload['password'] = 'ابتثجحخد'
        self.join()
        self.client.post('/auth/logout')
        response = self.client.post('/auth/login', data={'username':self.payload['email'],'password':self.payload['password']})
        self.assertEqual(response.status_code, 200)

    def test_admin_issue_is_origin_protected_hash_only_and_shown_once(self):
        self.assertEqual(self.client.post('/api/admin/tester-invitations', json={'email':self.payload['email']}, headers={'Authorization':self.admin['Authorization']}).status_code, 403)
        response = self.client.post('/api/admin/tester-invitations', json={'email':self.payload['email']}, headers=self.admin)
        self.assertEqual(response.status_code, 200, response.text)
        token = response.json()['link'].split('#invite=')[1]
        row = self.db.query(TesterInvitation).one()
        self.assertEqual(row.token_hash, service.digest(token)); self.assertNotEqual(row.token_hash, token)
        listing = self.client.get('/api/admin/tester-invitations', headers=self.admin)
        self.assertNotIn(token, listing.text); self.assertNotIn('token_hash', listing.text)
        self.assertEqual(listing.headers['cache-control'], 'no-store')
        self.assertEqual(self.client.post('/api/admin/tester-invitations', json={'email':self.payload['email'].upper()}, headers=self.admin).status_code, 409)

    def test_invalid_expired_used_revoked_tokens_are_generic_and_no_email_leaks(self):
        invitation_id, token = self.issue()
        check = lambda tok: self.client.post('/auth/tester-invitations/check', json={'token':tok}, headers={'Origin':ORIGIN})
        self.assertNotIn(self.payload['email'], check(token).text)
        invalid = check('x'*43); self.assertEqual(invalid.status_code, 410)
        row = self.db.get(TesterInvitation, invitation_id); row.expires_at = datetime.now(timezone.utc)-timedelta(seconds=1); self.db.commit()
        self.assertEqual(check(token).json(), invalid.json())
        service.revoke(self.db, invitation_id, 1)
        self.assertEqual(check(token).json(), invalid.json())
        self.assertEqual(check(token).headers['cache-control'], 'no-store')

    def test_wrong_email_and_invalid_password_do_not_consume_invitation_or_echo_secrets(self):
        invitation_id, token = self.issue()
        wrong = self.client.post('/auth/tester-invitations/redeem', json=dict(self.payload, token=token, email='wrong@fixture.test'), headers={'Origin':ORIGIN})
        self.assertEqual(wrong.status_code, 422)
        for password in ('short7!', 'أ'*7, 'أ'*40, 'x'*73):
            response = self.client.post('/auth/tester-invitations/redeem', json=dict(self.payload, token=token, password=password), headers={'Origin':ORIGIN})
            self.assertEqual(response.status_code, 422); self.assertNotIn(token, response.text); self.assertNotIn(password, response.text)
            self.assertIn('at least 8 characters', response.json()['detail'])
        self.assertIsNone(self.db.get(TesterInvitation, invitation_id).redeemed_at)
        self.assertEqual(self.db.query(User).count(), 1); self.assertEqual(self.db.query(Org).count(), 1)

    def test_duplicate_redemption_is_serialized_and_cannot_create_two_workspaces(self):
        invitation_id, token = self.issue(); barrier = threading.Barrier(2)
        def attempt(_):
            with Session(engine) as db:
                barrier.wait(timeout=10)
                try: service.redeem(db, token=token, **self.payload); return 200
                except HTTPException as error: return error.status_code
        with ThreadPoolExecutor(2) as pool: results = list(pool.map(attempt, range(2)))
        self.assertEqual(sorted(results), [200,410])
        self.assertEqual(self.db.query(User).count(), 2); self.assertEqual(self.db.query(Org).count(), 2)
        self.assertEqual(self.db.query(OrgMember).count(), 1)

    def test_concurrent_issue_produces_only_one_valid_invitation(self):
        barrier = threading.Barrier(2)
        def attempt(_):
            with Session(engine) as db:
                barrier.wait(timeout=10)
                try: service.issue(db, email=self.payload['email'], admin_id=1); return 200
                except HTTPException as error: return error.status_code
        with ThreadPoolExecutor(2) as pool: results = list(pool.map(attempt, range(2)))
        self.assertEqual(sorted(results), [200,409]); self.assertEqual(self.db.query(TesterInvitation).count(), 1)

    def test_revocation_invalidates_existing_session_key_and_background_account_preserves_work(self):
        invitation_id, user, response = self.join(); account = self.fixture_work(user)
        import hashlib
        self.db.add(ApiKey(org_id=user.active_org_id, name='Synthetic', key_hash=hashlib.sha256(b'fixture-scope-key').hexdigest())); self.db.commit()
        service.revoke(self.db, invitation_id, 1)
        self.assertEqual(self.client.get('/auth/me').status_code, 401)
        self.client.cookies.clear()
        self.assertEqual(self.client.get('/scope', headers={'X-API-Key':'fixture-scope-key'}).status_code, 401)
        with self.assertRaises(HTTPException): require_account(self.db, user.active_org_id, account.id, active=True)
        self.assertFalse(self.db.query(TopicAutomation).one().enabled)
        posts = self.db.query(Post).all(); self.assertEqual(len(posts), 4)
        self.assertEqual({p.status for p in posts}, {'drafted','published','publish_unknown','publishing'})
        self.assertTrue(all(p.caption == 'Keep exact draft' for p in posts))
        self.assertIsNone(next(p for p in posts if p.status=='drafted').scheduled_time)
        service.revoke(self.db, invitation_id, 1)  # repeat is safe
        self.assertEqual(self.db.query(Post).count(), 4)

    def test_expiry_denies_cookie_password_generation_and_background_before_spend(self):
        invitation_id, user, response = self.join(); account = self.fixture_work(user)
        expired = datetime.now(timezone.utc)-timedelta(seconds=1)
        user.tester_expires_at = expired; self.db.get(Org, user.active_org_id).tester_expires_at = expired; self.db.commit()
        self.assertEqual(self.client.get('/auth/me').status_code, 401)
        self.assertEqual(self.client.post('/auth/login', data={'username':user.email,'password':PASSWORD}).status_code, 401)
        with workspace_usage(user.active_org_id), self.assertRaises(HTTPException): usage_limits.reserve('image')
        self.assertEqual(self.db.query(UsageBucket).filter(UsageBucket.key.like('ai:%')).count(), 0)
        with self.assertRaises(HTTPException): require_account(self.db, user.active_org_id, account.id, active=True)
        self.assertEqual(self.db.query(Post).count(), 4)

    def test_replacing_unused_link_invalidates_old_link_and_never_promotes_existing_user(self):
        invitation_id, token = self.issue(); service.revoke(self.db, invitation_id, 1)
        row, replacement = service.issue(self.db, email=self.payload['email'], admin_id=1)
        with self.assertRaises(HTTPException): service.pending(self.db, token)
        self.assertEqual(service.pending(self.db, replacement).id, row.id)
        with self.assertRaises(HTTPException): service.issue(self.db, email='ADMIN@fixture.test', admin_id=1)
        self.assertEqual(self.db.query(User).count(), 1)

    def test_transaction_failure_keeps_invitation_redeemable_and_no_partial_user(self):
        invitation_id, token = self.issue()
        real = service.provision_creator
        def interrupted(*args, **kwargs):
            real(*args, **kwargs)
            raise RuntimeError('Synthetic interruption')
        with patch.object(service, 'provision_creator', interrupted), self.assertRaises(RuntimeError):
            service.redeem(self.db, token=token, **self.payload)
        self.assertEqual(self.db.query(User).count(), 1); self.assertEqual(self.db.query(Org).count(), 1)
        self.assertEqual(service.state(self.db.get(TesterInvitation, invitation_id)), 'pending')

    def test_migration_from_absence_and_repeat_preserves_existing_rows(self):
        with engine.begin() as c:
            c.execute(text('DROP TABLE tester_invitations'))
            c.execute(text('ALTER TABLE users DROP COLUMN tester_expires_at'))
            c.execute(text('ALTER TABLE orgs DROP COLUMN tester_expires_at, DROP COLUMN tester_revoked_at'))
            migrate(c); migrate(c)
        self.db.expire_all()
        self.assertEqual(self.db.get(User,1).email, 'admin@fixture.test')
        self.assertIsNone(self.db.get(User,1).tester_expires_at)
        self.assertEqual(self.db.get(Org,1).name, 'Existing private workspace')
        self.assertIsNone(self.db.get(Org,1).tester_revoked_at)
        self.assertEqual(self.db.query(TesterInvitation).count(), 0)

    def test_anonymous_and_workspace_keys_cannot_issue_or_view_invitations(self):
        import hashlib
        self.db.add(ApiKey(org_id=1, name='Synthetic', key_hash=hashlib.sha256(b'fixture-key').hexdigest())); self.db.commit()
        for headers in ({}, {'X-API-Key':'fixture-key'}):
            self.assertEqual(self.client.get('/api/admin/tester-invitations', headers=headers).status_code, 401)
            self.assertEqual(self.client.get('/admin/testers', headers=headers).status_code, 401)
        page = self.client.get('/join')
        self.assertEqual(page.status_code, 200); self.assertIn("frame-ancestors 'none'", page.headers['content-security-policy'])
        self.assertNotIn('https://', page.text)

    def test_expired_pilot_blocks_canonical_publish_and_automation_before_provider(self):
        from app.services import post_service, publisher, automation_runner
        invitation_id, user, response = self.join(); self.fixture_work(user)
        self.db.get(Org,user.active_org_id).tester_expires_at = datetime.now(timezone.utc)-timedelta(seconds=1)
        post = self.db.query(Post).filter_by(status='scheduled').one()
        post.media_url = 'https://res.cloudinary.com/fixture/image/upload/test.jpg'
        self.db.commit()
        with patch.object(publisher, 'publish_to_instagram') as publish, patch.object(automation_runner, 'pick_topic') if hasattr(automation_runner, 'pick_topic') else patch('app.services.rotation_engine.pick_topic') as pick:
            result = post_service.publish_post(self.db,post.id,user.active_org_id)
            self.assertEqual(result.status_code,403); publish.assert_not_called()
            self.assertIsNone(automation_runner.run_automation_once(self.db,self.db.query(TopicAutomation).one().id))
            pick.assert_not_called()
        self.assertEqual(self.db.get(Post,post.id).status,'scheduled')

    def test_expired_tester_cannot_sign_in_through_verified_google(self):
        import asyncio
        from types import SimpleNamespace
        from unittest.mock import AsyncMock
        from app.routes import auth_google
        import app.main as main
        invitation_id, user, response = self.join()
        user.tester_expires_at=datetime.now(timezone.utc)-timedelta(seconds=1);self.db.commit()
        with patch.object(main, 'is_prod', False, create=True), patch.object(auth_google.oauth.google, 'authorize_access_token', AsyncMock(return_value={'userinfo':{'sub':'synthetic-google-id','email':user.email,'email_verified':True}})):
            with self.assertRaises(HTTPException) as caught:
                asyncio.run(auth_google.google_auth(SimpleNamespace(scope={}),self.db))
        self.assertEqual(caught.exception.status_code,403);self.assertIsNone(user.google_id)

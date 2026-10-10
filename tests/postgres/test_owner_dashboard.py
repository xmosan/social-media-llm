"""Owner-only UI and platform APIs against disposable PostgreSQL, with no providers."""
from datetime import datetime, timedelta, timezone
import hashlib
import unittest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.db import engine, get_db
from app.config import settings
from app.models import Base, User, Org, OrgMember, ApiKey, Post, IGAccount, InboundMessage, TesterInvitation, TopicAutomation, WaitlistEntry, ContentSource
from app.routes import public, admin, admin_diag, admin_backup, tester_access, creator_feedback, admin_library, auth
from app.api.routes import admin_panel, waitlist
from app.security.auth import create_access_token
from app.services import scheduler

ORIGIN = 'https://app.sabeelstudio.com'


class OwnerDashboardChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert engine.url.database == 'sabeel_test' and engine.url.query['host'].startswith('/tmp/sabeel-pg-test-')
        Base.metadata.create_all(engine)

    def setUp(self):
        owner = patch.object(settings, 'platform_owner_email', 'owner@fixture.test')
        owner.start(); self.addCleanup(owner.stop)
        with engine.begin() as c:
            c.execute(text('TRUNCATE '+', '.join('"'+t.name+'"' for t in Base.metadata.sorted_tables)+' RESTART IDENTITY CASCADE'))
        self.db = Session(engine, expire_on_commit=False); self.addCleanup(self.db.close)
        self.db.add_all([Org(id=1,name='Owner workspace'),Org(id=2,name='Creator workspace')]);self.db.flush()
        self.db.add_all([User(id=1,email='owner@fixture.test',is_superadmin=True,active_org_id=1),
                         User(id=2,email='creator@fixture.test',active_org_id=2),
                         User(id=3,email='legacy-admin@fixture.test',is_superadmin=True,active_org_id=2)])
        self.db.flush()
        self.db.add_all([OrgMember(org_id=1,user_id=1,role='owner'),OrgMember(org_id=2,user_id=2,role='owner'),OrgMember(org_id=2,user_id=3,role='member')])
        self.db.add(ApiKey(org_id=2,name='Fixture key',key_hash=hashlib.sha256(b'fixture-workspace-key').hexdigest()))
        self.db.add(IGAccount(id=1,org_id=2,name='Fixture',ig_user_id='123',access_token='synthetic-only',active=True))
        self.db.commit()
        self.app=FastAPI()
        for router in (public.router,admin.router,admin_panel.router,admin_diag.router,admin_backup.router,waitlist.router,tester_access.router,creator_feedback.router,admin_library.router,auth.router):self.app.include_router(router)
        self.app.dependency_overrides[get_db]=lambda:self.db
        self.client=TestClient(self.app,base_url=ORIGIN);self.addCleanup(self.client.close)
        scheduler.reload_automation_jobs.reset_mock()

    def headers(self,id=1):return {'Authorization':'Bearer '+create_access_token({'sub':str(id)})}

    def test_single_dashboard_owner_access_private_headers_and_self_hosted_assets(self):
        self.assertEqual(sum(r.path=='/admin' for r in self.app.routes),1)
        r=self.client.get('/admin',headers=self.headers())
        self.assertEqual(r.status_code,200);self.assertIn('Owner dashboard',r.text)
        self.assertNotIn('Strategic Control',r.text);self.assertNotIn('cdn.tailwindcss',r.text)
        self.assertIn('/static/owner-dashboard.js',r.text)
        self.assertEqual(r.headers['cache-control'],'no-store')
        self.assertIn("frame-ancestors 'none'",r.headers['content-security-policy'])
        for path in ('/admin/login','/admin/register'):
            r=self.client.get(path,follow_redirects=False);self.assertEqual(r.status_code,303);self.assertEqual(r.headers['location'],'/login')
        self.assertEqual(self.client.get('/admin/backup-db',headers=self.headers()).status_code,405)

    def test_platform_routes_reject_anonymous_creator_legacy_admin_and_both_api_keys(self):
        reads=('/admin','/admin/users','/admin/inquiries','/admin/testers','/admin/feedback','/admin/debug/logging','/admin/debug/version','/admin/config/export','/admin/download-backup','/api/admin/diag/media-diagnostic?url=https://example.test/image.jpg',
               '/api/admin/overview','/api/admin/diagnostics','/api/admin/automations','/api/admin/ig-accounts','/api/admin/messages','/api/admin/failed-posts',
               '/api/waitlist/all','/api/waitlist/export','/api/contact/all')
        # /api/contact/all has its own coverage in ContactPrivacyChecks.
        for h,code in (({},401),(self.headers(2),403),(self.headers(3),403),({'X-API-Key':'fixture-workspace-key'},401),({'X-API-Key':settings.admin_api_key},401)):
            for path in reads[:-1]:
                with self.subTest(path=path,code=code):self.assertEqual(self.client.get(path,headers=h).status_code,code)
            for path in ('/admin/backup-now','/api/admin/automations/1/run','/api/admin/sync/full-quran'):
                with self.subTest(path=path,code=code):self.assertEqual(self.client.post(path,headers=h).status_code,code)
            self.assertEqual(self.client.patch('/api/admin/messages/1',json={'status':'resolved'},headers=h).status_code,code)
        scheduler.reload_automation_jobs.assert_not_called()

    def test_owner_requires_configured_identity_active_account_and_role(self):
        with patch.object(settings,'platform_owner_email',None):self.assertEqual(self.client.get('/api/admin/overview',headers=self.headers()).status_code,403)
        with patch.object(settings,'platform_owner_email',' OWNER@FIXTURE.TEST '):self.assertEqual(self.client.get('/api/admin/overview',headers=self.headers()).status_code,200)
        u=self.db.get(User,1);u.is_superadmin=False;self.db.commit()
        self.assertEqual(self.client.get('/admin',headers=self.headers()).status_code,403)
        u.is_superadmin=True;u.is_active=False;self.db.commit()
        self.assertEqual(self.client.get('/admin',headers=self.headers()).status_code,401)

    def test_cookie_write_requires_same_origin_and_message_state_is_validated(self):
        m=InboundMessage(email='help@fixture.test',message='Fixture',status='received');self.db.add(m);self.db.commit()
        path=f'/api/admin/messages/{m.id}';self.client.cookies.set('access_token',create_access_token({'sub':'1'}))
        for origin in ('','https://untrusted.example',ORIGIN+'.evil.example'):
            r=self.client.patch(path,json={'status':'resolved'},headers={'Origin':origin});self.assertEqual(r.status_code,403)
        self.db.refresh(m);self.assertEqual(m.status,'received')
        r=self.client.patch(path,json={'status':'resolved'},headers={'Origin':ORIGIN});self.assertEqual(r.status_code,200)
        self.db.refresh(m);self.assertEqual(m.status,'resolved')
        self.assertEqual(r.headers['cache-control'],'no-store')
        self.assertEqual(self.client.patch(path,json={'status':'invented'},headers={'Origin':ORIGIN}).status_code,422)

    def test_summary_counts_invitation_state_feedback_and_unknown_publication(self):
        now=datetime.now(timezone.utc)
        for i,extra in enumerate(({}, {'expires_at':now-timedelta(days=1)}, {'revoked_at':now}, {'redeemed_at':now,'access_expires_at':now+timedelta(days=1)}, {'redeemed_at':now,'access_expires_at':now-timedelta(days=1)})):
            data=dict(id=str(i),email=f'{i}@fixture.test',token_hash=str(i)*64,created_by=1,created_at=now,expires_at=now+timedelta(days=1),pilot_days=30);data.update(extra);self.db.add(TesterInvitation(**data))
        self.db.add_all([InboundMessage(email='help@fixture.test',message='Support',status='received'),InboundMessage(email='pilot@fixture.test',message='Feedback',source='creator_pilot',status='received')])
        self.db.add_all([Post(org_id=2,ig_account_id=1,status='publish_unknown',last_error='Unconfirmed fixture'),Post(org_id=2,ig_account_id=1,status='failed',flags={'unrelated':True},last_error='Retained fixture error')]);self.db.commit()
        d=self.client.get('/api/admin/overview',headers=self.headers()).json()
        self.assertEqual(d['creators'],2);self.assertEqual(d['pilot'],{'pending':1,'active':1});self.assertEqual(d['inbox'],{'feedback':1,'support_pending':1});self.assertEqual(d['posts']['publish_unknown'],1)
        messages=self.client.get('/api/admin/messages',headers=self.headers()).json()['items'];self.assertEqual(len(messages),1);self.assertEqual(messages[0]['message'],'Support')
        failures=self.client.get('/api/admin/failed-posts',headers=self.headers()).json()['items'];self.assertEqual(len(failures),2);self.assertIn('Retained fixture error',{f['error'] for f in failures})
        for path in ('/api/admin/messages?limit=999','/api/admin/failed-posts?limit=-1','/api/waitlist/all?limit=999'):
            self.assertEqual(self.client.get(path,headers=self.headers()).status_code,422)

    def test_diagnostics_never_claim_provider_or_restore_verification(self):
        with patch.object(scheduler,'_global_scheduler',None,create=True):
            r=self.client.get('/api/admin/diagnostics',headers=self.headers())
        self.assertEqual(r.status_code,200,r.text);d=r.json();self.assertEqual(d['database'],'connected')
        self.assertNotIn('database_url',d['environment']);self.assertNotIn('backup_verified',r.text)
        self.assertEqual(r.headers['cache-control'],'no-store')
        self.assertEqual(self.client.get('/api/waitlist/export',headers=self.headers()).headers['cache-control'],'no-store')

    def test_creator_library_and_normal_me_remain_workspace_scoped(self):
        for id in (2,3):
            h=self.headers(id);r=self.client.get('/auth/me',headers=h)
            self.assertEqual(r.status_code,200);self.assertFalse(r.json()['is_superadmin'])
            # Same workspace endpoint remains accessible despite its historic /admin prefix.
            r=self.client.get('/api/admin/library/sources',headers=h)
            self.assertIn(r.status_code,(200,307),r.text)
            r=self.client.get('/api/admin/library/sources',headers={**h,'X-Org-Id':'1'})
            self.assertEqual(r.status_code,403,r.text)

    def test_pause_persists_and_resume_uses_existing_schedule_and_account_validation(self):
        a=TopicAutomation(org_id=2,ig_account_id=1,name='Fixture plan',topic_prompt='Fixture',enabled=True)
        self.db.add(a);self.db.commit();path=f'/api/admin/automations/{a.id}'
        self.assertEqual(self.client.patch(path,json={'enabled':'false'},headers=self.headers()).status_code,422)
        self.assertEqual(self.client.patch(path,json={'enabled':False},headers=self.headers()).status_code,200)
        self.db.refresh(a);self.assertFalse(a.enabled);scheduler.reload_automation_jobs.assert_called_once()
        self.db.get(IGAccount,1).active=False;self.db.commit()
        self.assertEqual(self.client.patch(path,json={'enabled':True},headers=self.headers()).status_code,422)
        self.db.refresh(a);self.assertFalse(a.enabled)

    def test_waitlist_notes_status_persist_and_invalid_updates_leave_data_intact(self):
        entry=WaitlistEntry(email='future@fixture.test',name='Fixture',status='active')
        self.db.add(entry);self.db.commit();path=f'/api/waitlist/{entry.id}'
        r=self.client.patch(path,json={'status':'contacted','admin_notes':'Private fixture note'},headers=self.headers())
        self.assertEqual(r.status_code,200)
        saved=self.client.get('/api/waitlist/all',headers=self.headers()).json()['items'][0]
        self.assertEqual(saved['admin_notes'],'Private fixture note');self.assertEqual(saved['status'],'contacted')
        self.assertEqual(self.client.patch(path,json={'status':'not-a-status'},headers=self.headers()).status_code,422)
        self.assertEqual(self.client.patch(path,json={'email':'changed@fixture.test'},headers=self.headers()).status_code,422)
        self.db.refresh(entry);self.assertEqual(entry.email,'future@fixture.test');self.assertEqual(entry.status,'contacted')

    def test_global_library_writes_require_owner_and_cookie_origin_but_creator_reads_stay_open(self):
        source=ContentSource(name='Global fixture',source_type='manual',org_id=None)
        self.db.add(source);self.db.commit();path=f'/api/admin/library/sources/{source.id}'
        self.assertEqual(self.client.patch(path,json={'name':'Changed'},headers=self.headers(3)).status_code,403)
        self.client.cookies.set('access_token',create_access_token({'sub':'1'}))
        self.assertEqual(self.client.patch(path,json={'name':'Changed'}).status_code,403)
        self.db.refresh(source);self.assertEqual(source.name,'Global fixture')
        self.assertEqual(self.client.patch(path,json={'name':'Changed'},headers={'Origin':ORIGIN}).status_code,200)

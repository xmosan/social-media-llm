"""Synthetic Meta onboarding; no live provider, production DB or account changes."""
import asyncio
import base64
from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
from unittest.mock import AsyncMock, Mock, patch
import unittest
import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware
from app.config import settings
from app.db import get_db
from app.models import User, Org, OrgMember, IGAccount, InstagramConnectionAttempt as Attempt
from app.routes import auth_ig, ig_accounts, app_pages
from app.security.auth import get_current_user
from app.security.instagram_session import LegacyInstagramSessionCleanup
from app.services import instagram_connection as connection
from app.services.instagram_auth import InstagramAuthService, InstagramAuthError
from app.services.publisher import GRAPH_URL
from test_security import DatabaseCase

ORIGIN = 'https://app.sabeelstudio.com'
ACCOUNTS = [{'ig_user_id':'111','fb_page_id':'222','username':'fixture_creator','name':'<Fixture & creator>','profile_picture_url':None}]
TOKEN = 'synthetic-provider-token-never-real'


class InstagramConnectionChecks(DatabaseCase):
    def setUp(self):
        super().setUp()
        IGAccount.__table__.create(self.engine); Attempt.__table__.create(self.engine)
        self.db.add_all([Org(id=1,name='Own'),Org(id=2,name='Other')]);self.db.flush()
        self.user=User(id=1,email='owner@fixture.test',name='Fixture',is_active=True,active_org_id=1)
        self.other=User(id=2,email='other@fixture.test',name='Other',is_active=True,active_org_id=2)
        self.db.add_all([self.user,self.other]);self.db.flush()
        self.db.add_all([OrgMember(user_id=1,org_id=1,role='owner'),OrgMember(user_id=2,org_id=2,role='owner')])
        self.existing=IGAccount(org_id=1,ig_user_id='999',name='Existing',access_token='synthetic-old-token',active=True)
        self.db.add(self.existing);self.db.commit()
        app=FastAPI();app.include_router(auth_ig.router);app.include_router(auth_ig.meta_alias_router)
        app.include_router(ig_accounts.accounts_router);app.include_router(ig_accounts.router);app.include_router(app_pages.router)
        app.add_middleware(LegacyInstagramSessionCleanup)
        app.add_middleware(SessionMiddleware,secret_key=settings.secret_key,https_only=True,same_site='lax')
        app.dependency_overrides[get_db]=lambda:self.db
        app.dependency_overrides[get_current_user]=lambda:self.user
        self.client=TestClient(app,base_url=ORIGIN,follow_redirects=False);self.addCleanup(self.client.close)
        service=auth_ig.instagram_auth_service
        for manager in (patch.object(auth_ig,'check_auth_attempt'), patch.object(service,'client_id','fixture-app'),
                        patch.object(service,'client_secret','fixture-secret'),patch.object(service,'redirect_uri',ORIGIN+'/auth/instagram/callback'),
                        patch.object(service,'exchange_code_for_token',AsyncMock(return_value='synthetic-short')),
                        patch.object(service,'get_long_lived_token',AsyncMock(return_value={'access_token':TOKEN,'expires_at':datetime.now(timezone.utc)+timedelta(days=3)})),
                        patch.object(service,'discover_ig_business_account',AsyncMock(return_value=ACCOUNTS))):
            manager.start();self.addCleanup(manager.stop)

    def start(self):
        r=self.client.get('/auth/instagram/login');self.assertEqual(r.status_code,303,r.text)
        q=parse_qs(urlsplit(r.headers['location']).query)
        self.assertEqual(q['redirect_uri'],[ORIGIN+'/auth/instagram/callback'])
        self.assertIn(GRAPH_URL.rsplit('/',1)[-1],r.headers['location'])
        return q['state'][0]

    def ready(self):
        state=self.start();r=self.client.get('/auth/instagram/callback',params={'state':state,'code':'synthetic-code'})
        self.assertEqual(r.status_code,303);self.assertEqual(r.headers['location'],'/select-account')
        return state

    def select(self,payload=None,**kwargs):
        return self.client.post('/accounts/select',json=payload if payload is not None else [{'ig_user_id':'111','page_id':'222'}],headers=kwargs or {'Origin':ORIGIN})

    def test_happy_path_cookie_has_only_handle_selection_preserves_existing_and_expiry(self):
        self.ready()
        cookie=json.loads(base64.b64decode(self.client.cookies.get('session').split('.')[0]))
        self.assertEqual(set(cookie),{'ig_connection'});self.assertNotIn(TOKEN,json.dumps(cookie))
        row=self.db.query(Attempt).one();self.assertNotIn(TOKEN,row.encrypted_payload)
        available=self.client.get('/accounts/available');self.assertEqual(available.json(),ACCOUNTS)
        self.assertNotIn(TOKEN,available.text)
        self.assertEqual(available.headers["cache-control"],"no-store")
        self.assertEqual(available.headers["referrer-policy"],"no-referrer")
        self.assertTrue(self.select().json()['ok']);self.db.refresh(self.existing);self.assertTrue(self.existing.active)
        account=self.db.query(IGAccount).filter_by(ig_user_id='111').one()
        self.assertEqual(account.access_token,TOKEN);self.assertEqual(account.org_id,1)
        self.assertLess(account.expires_at.replace(tzinfo=timezone.utc),datetime.now(timezone.utc)+timedelta(days=4))
        self.assertEqual(self.db.query(Attempt).count(),0)
        self.assertEqual(self.select().status_code,401)

    def test_missing_wrong_and_replayed_state_never_exchange(self):
        state=self.start();exchange=auth_ig.instagram_auth_service.exchange_code_for_token
        for params in ({'code':'fixture'},{'state':'x'*43,'code':'fixture'}):
            self.assertEqual(self.client.get('/auth/instagram/callback',params=params).status_code,400)
        exchange.assert_not_called()
        self.client.get('/auth/instagram/callback',params={'state':state,'code':'fixture'})
        self.assertEqual(self.client.get('/auth/instagram/callback',params={'state':state,'code':'fixture'}).status_code,400)
        self.assertEqual(exchange.await_count,1)

    def test_cross_browser_state_cannot_claim(self):
        state=self.start();self.client.cookies.clear()
        self.assertEqual(self.client.get('/auth/instagram/callback',params={'state':state,'code':'fixture'}).status_code,401)
        auth_ig.instagram_auth_service.exchange_code_for_token.assert_not_called()

    def test_cancel_consumes_flow_without_changing_accounts(self):
        state=self.start();r=self.client.get('/auth/meta/callback',params={'state':state,'error':'access_denied'})
        self.assertEqual(r.status_code,303);self.assertIn('cancelled',r.headers['location'])
        auth_ig.instagram_auth_service.exchange_code_for_token.assert_not_called()
        self.assertEqual(self.db.query(Attempt).count(),0);self.assertTrue(self.existing.active)

    def test_provider_error_is_sanitized_and_existing_connection_survives(self):
        state=self.start();auth_ig.instagram_auth_service.exchange_code_for_token.side_effect=RuntimeError('private-token-and-code')
        r=self.client.get('/auth/instagram/callback',params={'state':state,'code':'fixture'})
        self.assertEqual(r.status_code,303);self.assertEqual(r.headers['location'],'/select-account?connection=unavailable')
        self.assertEqual(self.db.query(Attempt).count(),0);self.assertTrue(self.existing.active)

    def test_no_accounts_callback_offers_restart_without_changing_existing(self):
        state=self.start();auth_ig.instagram_auth_service.discover_ig_business_account.return_value=[]
        r=self.client.get('/auth/instagram/callback',params={'state':state,'code':'fixture'})
        self.assertEqual(r.headers['location'],'/select-account?connection=no-accounts')
        self.assertEqual(self.db.query(Attempt).count(),0);self.assertTrue(self.existing.active)


    def test_expired_callback_and_discovery_are_rejected(self):
        state=self.start();row=self.db.query(Attempt).one();row.expires_at=datetime.now(timezone.utc)-timedelta(seconds=1);self.db.commit()
        self.assertEqual(self.client.get('/auth/instagram/callback',params={'state':state,'code':'fixture'}).status_code,400)
        self.ready();row=self.db.query(Attempt).one();row.expires_at=datetime.now(timezone.utc)-timedelta(seconds=1);self.db.commit()
        self.assertEqual(self.client.get('/accounts/available').status_code,401)
        self.assertEqual(self.select().status_code,401)

    def test_user_switch_and_revoked_membership_cannot_reuse_discovery(self):
        self.ready();original=self.user;self.user=self.other
        self.assertEqual(self.client.get('/accounts/available').status_code,401)
        self.assertEqual(self.select().status_code,401)
        self.user=original;self.db.query(OrgMember).filter_by(user_id=1).delete();self.db.commit()
        self.assertEqual(self.client.get('/accounts/available').status_code,403)
        self.assertEqual(self.select().status_code,403)

    def test_workspace_switch_requires_new_flow_even_with_membership(self):
        state=self.start();self.db.add(OrgMember(user_id=1,org_id=2,role='member'));self.user.active_org_id=2;self.db.commit()
        self.assertEqual(self.client.get('/auth/instagram/callback',params={'state':state,'code':'fixture'}).status_code,400)
        auth_ig.instagram_auth_service.exchange_code_for_token.assert_not_called()

    def test_invalid_or_empty_selection_is_atomic_and_can_retry(self):
        self.ready()
        for payload in ([],[{'ig_user_id':'111','page_id':'wrong'}],[{'ig_user_id':'111','page_id':'222'},{'ig_user_id':'not-discovered','page_id':'222'}],[{'ig_user_id':'111','page_id':'222'}]*2):
            self.assertEqual(self.select(payload).status_code,422)
            self.assertEqual(self.db.query(IGAccount).count(),1);self.db.refresh(self.existing);self.assertTrue(self.existing.active)
        self.assertEqual(self.select().status_code,200)

    def test_cross_origin_selection_rejected_before_mutation(self):
        self.ready();self.assertEqual(self.select(Origin='https://another.example').status_code,403)
        self.assertEqual(self.db.query(IGAccount).count(),1)

    def test_legacy_cookie_no_longer_authorizes_options_or_connect(self):
        self.client.cookies.set('temp_ig_token',TOKEN,domain='app.sabeelstudio.com',path='/')
        self.assertEqual(self.client.get('/ig-accounts/meta-options').status_code,401)
        self.assertIsNone(self.client.cookies.get('temp_ig_token'))
        self.assertEqual(self.client.post('/ig-accounts/connect',json={'ig_user_id':'111'}).status_code,401)
        auth_ig.instagram_auth_service.discover_ig_business_account.assert_not_called()

    def test_legacy_connect_uses_same_ready_handoff(self):
        self.ready();r=self.client.post('/ig-accounts/connect',json={'ig_user_id':'111'},headers={'Origin':ORIGIN})
        self.assertEqual(r.status_code,200);self.assertNotIn(TOKEN,r.text)
        self.assertEqual(self.db.query(Attempt).count(),0)

    def test_reconnect_updates_same_account_without_losing_identity(self):
        self.existing.ig_user_id='111';self.db.commit();old_id=self.existing.id
        self.ready();self.assertEqual(self.select().status_code,200)
        self.assertEqual(self.db.query(IGAccount).count(),1);self.db.refresh(self.existing)
        self.assertEqual(self.existing.id,old_id);self.assertEqual(self.existing.access_token,TOKEN)


    def test_old_signed_session_credentials_are_removed_on_any_request(self):
        from itsdangerous import TimestampSigner
        payload={'temp_ig_token':TOKEN,'discovered_accounts':ACCOUNTS,'google_auth_fixture':'preserved'}
        signed=TimestampSigner(settings.secret_key).sign(base64.b64encode(json.dumps(payload).encode())).decode()
        self.client.cookies.set('session',signed,domain='app.sabeelstudio.com',path='/')
        self.assertEqual(self.client.get('/accounts/connected').status_code,200)
        decoded=json.loads(base64.b64decode(self.client.cookies.get('session').split('.')[0]))
        self.assertEqual(decoded,{'google_auth_fixture':'preserved'})

    def test_legacy_finalizer_cannot_accept_tokens_or_revoked_workspace(self):
        payload={'orgName':'Fixture','contentMode':'quran','autoTopic':'Fixture topic','autoTime':'09:00'}
        self.assertEqual(self.client.post('/api/onboarding/finalize',json=payload|{'igAccessToken':TOKEN}).status_code,400)
        self.assertEqual(self.db.query(IGAccount).count(),1)
        self.db.query(OrgMember).filter_by(user_id=1).delete();self.db.commit()
        self.assertEqual(self.client.post('/api/onboarding/finalize',json=payload).status_code,403)

    def test_disconnect_and_account_read_preserve_identity_and_do_not_reactivate(self):
        original_id=self.existing.id
        self.assertEqual(self.client.post('/auth/instagram/disconnect',headers={'Origin':ORIGIN}).status_code,200)
        result=self.client.get('/ig-accounts/active')
        self.assertEqual(result.status_code,200);self.assertFalse(result.json()['active'])
        self.db.refresh(self.existing)
        self.assertEqual(self.existing.id,original_id);self.assertFalse(self.existing.active)
        self.assertEqual(self.existing.access_token,'');self.assertFalse(self.user.has_connected_instagram)
        account,accounts,connected=app_pages.get_active_context(self.db,self.user,1)
        self.assertEqual(account.id,original_id);self.assertFalse(connected)
        self.assertFalse(account.active);self.assertEqual(len(accounts),1)


class MetaProviderChecks(unittest.TestCase):
    def test_redirect_validation_rejects_substring_hosts_and_query_injection(self):
        service=InstagramAuthService();service.client_id='fixture';service.client_secret='fixture'
        for uri in (ORIGIN+'.evil.test/auth/instagram/callback',ORIGIN+'/auth/instagram/callback?next=evil','http://app.sabeelstudio.com/auth/instagram/callback'):
            service.redirect_uri=uri
            with self.assertRaises(Exception):service.get_auth_url('fixture-state')

    def test_expiry_is_provider_returned_or_unknown_never_invented(self):
        service=InstagramAuthService()
        with patch.object(service,'_get',AsyncMock(return_value={'access_token':TOKEN})):
            self.assertIsNone(asyncio.run(service.get_long_lived_token('fixture'))['expires_at'])
        with patch.object(service,'_get',AsyncMock(return_value={'access_token':TOKEN,'expires_in':-1})):
            with self.assertRaises(InstagramAuthError):asyncio.run(service.get_long_lived_token('fixture'))

    def test_discovery_paginates_on_trusted_endpoint_not_returned_url(self):
        service=InstagramAuthService();calls=[]
        def transport(request):
            calls.append(request)
            first='after' not in request.url.params
            return httpx.Response(200,json={'data':[{'id':'222' if first else '333','instagram_business_account':{'id':'111' if first else '444','username':'fixture'}}],
                **({'paging':{'next':'https://malicious.example/steal','cursors':{'after':'next-page'}}} if first else {})})
        original=httpx.AsyncClient
        with patch('app.services.instagram_auth.httpx.AsyncClient',lambda **kw:original(transport=httpx.MockTransport(transport),**kw)):
            result=asyncio.run(service.discover_ig_business_account(TOKEN))
        self.assertEqual(len(result),2);self.assertEqual(len(calls),2)
        for request in calls:
            self.assertEqual(request.url.host,'graph.facebook.com');self.assertNotIn(TOKEN,str(request.url))
            self.assertEqual(request.headers['Authorization'],'Bearer '+TOKEN)
            self.assertNotIn('access_token',request.url.params['fields'])

    def test_malformed_or_provider_denied_discovery_never_returns_partial_accounts(self):
        service=InstagramAuthService()
        for response in ({'data':{}},{'data':[{'id':'bad-path/secret'}]},{'error':{'message':'sensitive'}}):
            with patch.object(service,'_get',AsyncMock(return_value=response)):
                with self.assertRaises(InstagramAuthError):asyncio.run(service.discover_ig_business_account(TOKEN))

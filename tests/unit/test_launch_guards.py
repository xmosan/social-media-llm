"""Launch guard contracts; no network or production database access."""
import ast
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
import unittest
from fastapi import FastAPI, Depends, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from app.config import settings, Settings
from app.models import User, Org, OrgMember
from app.db import get_db
from app.routes import auth, auth_google, public, studio
from app.services import usage_limits as limits, image_provider, text_provider, visual_service
from app.security.usage_context import workspace_usage, current_scope, UsageContextMiddleware
from app.security.rbac import get_current_org_id
from app.security.auth import create_access_token
from test_security import DatabaseCase


class AdmissionTests(DatabaseCase):
    def setUp(self):
        super().setUp()
        application = FastAPI()
        application.include_router(auth.router)
        application.include_router(auth_google.router)
        application.include_router(public.router)
        application.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(application, base_url='https://testserver', follow_redirects=False)
        self.addCleanup(self.client.close)
        for stub in (patch.object(limits, 'check_auth_attempt'), patch('app.main.is_prod', True, create=True), patch.object(settings,'signup_enabled',False)):
            stub.start(); self.addCleanup(stub.stop)

    def google(self, **changes):
        info={'sub':'fixture-id','email':'creator@example.com','email_verified':True,'name':'Creator'}
        with patch.object(auth_google.oauth.google,'authorize_access_token',AsyncMock(return_value={'userinfo':info|changes})):
            return self.client.get('/auth/google/callback')

    def test_closed_registration_has_no_writes_or_hashing(self):
        with patch.object(auth,'get_password_hash') as hash_password:
            response=self.client.post('/auth/register',json={'email':'creator@example.com','password':'disposable-long-password','name':'Creator'})
        self.assertEqual(response.status_code,403);hash_password.assert_not_called()
        self.assertEqual(self.db.query(User).count(),0);self.assertEqual(self.db.query(Org).count(),0)
        self.assertNotIn('registerForm',self.client.get('/register').text)
        self.assertIn('private preview',self.client.get('/register').text)

    def test_new_google_account_cannot_bypass_closed_registration(self):
        response=self.google()
        self.assertEqual(response.status_code,303);self.assertEqual(response.headers['location'],'/login?error=registration_closed')
        self.assertNotIn('set-cookie',response.headers)
        self.assertEqual(self.db.query(User).count(),0);self.assertEqual(self.db.query(Org).count(),0)

    def test_verified_existing_google_login_works_but_disabled_and_conflicting_accounts_do_not(self):
        user=User(email='CREATOR@example.com',name='Fixture',is_active=True)
        self.db.add(user);self.db.commit()
        response=self.google();self.assertEqual(response.status_code,307)
        self.assertEqual(user.google_id,'fixture-id');self.assertIn('Secure',response.headers['set-cookie'])
        user.is_active=False;self.db.commit();self.assertEqual(self.google().status_code,403)
        user.is_active=True;user.google_id='another-google-account';self.db.commit()
        self.assertEqual(self.google().status_code,403)

    def test_unverified_missing_and_wrong_type_google_identity_cannot_link(self):
        for changes in ({'email_verified':False},{'email_verified':'true'},{'sub':None},{'email':None}):
            self.assertEqual(self.google(**changes).status_code,400)
        self.assertEqual(self.db.query(User).count(),0)

    def test_explicit_open_mode_provisions_one_workspace_with_no_privilege(self):
        with patch.object(settings,'signup_enabled',True):
            self.assertEqual(self.google().status_code,307)
        user=self.db.query(User).one();membership=self.db.query(OrgMember).one()
        self.assertTrue(user.is_active);self.assertFalse(user.is_superadmin)
        self.assertEqual(user.active_org_id,membership.org_id)
        self.assertEqual(membership.role,'owner')


class UsageContractTests(unittest.TestCase):
    def test_default_admission_is_closed_independent_of_landing_page(self):
        self.assertFalse(Settings(_env_file=None,coming_soon_mode=False).signup_enabled)

    def test_missing_context_and_paused_generation_never_dispatch(self):
        for kind in ('text','image'):
            with patch.object(limits,'_session') as session, self.assertRaises(HTTPException) as caught:
                limits.reserve(kind)
            self.assertEqual(caught.exception.status_code,403);session.assert_not_called()
        with workspace_usage(1), patch.object(settings,'ai_generation_enabled',False), patch.object(limits,'_session') as session, self.assertRaises(HTTPException) as caught:
            limits.reserve('image')
        self.assertEqual(caught.exception.status_code,503);session.assert_not_called()

    def test_limit_storage_failure_is_closed_and_private(self):
        failure=OperationalError('private-sql','private-params',Exception('private-details'))
        with workspace_usage(1), patch.object(limits,'_session',side_effect=failure), self.assertRaises(HTTPException) as caught:
            limits.reserve('image')
        self.assertEqual(caught.exception.status_code,503);self.assertNotIn('private',str(caught.exception))

    def test_provider_calls_never_happen_when_budget_is_denied(self):
        with patch.object(settings,'openai_api_key','fixture'), patch.object(limits,'reserve',side_effect=limits.UsageLimitError('Limit reached')), patch.object(image_provider,'generate_openai_image') as image, patch.object(text_provider,'request_text') as writing:
            for generate in (image_provider.generate_configured_image,text_provider.generate_text):
                with self.assertRaises(limits.UsageLimitError):generate('Synthetic fixture')
        image.assert_not_called();writing.assert_not_called()

    def test_overlong_input_and_missing_configuration_never_reserve(self):
        with patch.object(limits,'reserve') as reserve,patch.object(settings,'openai_api_key','fixture'):
            for generate,prompt in ((image_provider.generate_configured_image,'x'*12001),(text_provider.generate_text,'x'*40001)):
                with self.assertRaises(limits.UsageLimitError):generate(prompt)
            with patch.object(settings,'openai_api_key',None):
                with self.assertRaises(image_provider.ImageGenerationError):image_provider.generate_configured_image('fixture')
        reserve.assert_not_called()

    def test_fallback_needs_a_second_reservation_and_stops_when_denied(self):
        def attempt(kind):
            if gate.call_count==2:raise limits.UsageLimitError('Limit reached')
            return nullcontext()
        with patch.object(settings,'openai_api_key','fixture'),patch.object(limits,'paid_call',side_effect=attempt) as gate,patch.object(image_provider,'generate_openai_image',side_effect=image_provider.ImageGenerationError('unavailable',404)) as provider:
            with self.assertRaises(limits.UsageLimitError):image_provider.generate_configured_image('fixture')
        self.assertEqual(gate.call_count,2);provider.assert_called_once()

    def test_visual_facade_and_caption_route_preserve_actionable_limit_status(self):
        with patch.object(visual_service,'_generate_background_only',side_effect=limits.UsageLimitError('Wait for current generation',retry_after=15)),self.assertRaises(HTTPException) as caught:
            visual_service.generate_visual(visual_service.VisualRequest())
        self.assertEqual(caught.exception.status_code,429);self.assertEqual(caught.exception.headers['Retry-After'],'15')
        with patch.object(studio,'resolve_selected_source',return_value={'reference':'Exact fixture','translation_text':'Exact synthetic text'}),patch('app.services.quran_caption_service.generate_ai_caption_from_quran',side_effect=limits.UsageLimitError('Limit reached')),self.assertRaises(HTTPException) as caught:
            studio.studio_generate_caption({'source_type':'quran'},db=Mock(),org_id=1,user=SimpleNamespace(id=1))
        self.assertEqual(caught.exception.status_code,429)

    def test_worker_scope_replaces_request_scope_and_restores_it(self):
        from app.services import automation_runner
        db=Mock();db.get.return_value=SimpleNamespace(org_id=7)
        with workspace_usage(2),patch.object(automation_runner,'_run_automation_once',side_effect=lambda *args: current_scope.get().org_id):
            self.assertEqual(automation_runner.run_automation_once(db,1),7)
            self.assertEqual(current_scope.get().org_id,2)
        self.assertIsNone(current_scope.get())


class RequestScopeTests(DatabaseCase):
    def test_sync_dependency_binds_for_sync_and_async_handlers_without_request_leak(self):
        self.db.add_all([Org(id=1,name='First'),Org(id=2,name='Other'),User(id=1,email='user@example.test',is_active=True,active_org_id=1)])
        self.db.add(OrgMember(org_id=1,user_id=1));self.db.commit()
        app=FastAPI();app.add_middleware(UsageContextMiddleware)
        app.dependency_overrides[get_db]=lambda:self.db
        @app.get('/sync')
        def sync(org_id:int=Depends(get_current_org_id)):return {'org':current_scope.get().org_id}
        @app.get('/async')
        async def async_route(org_id:int=Depends(get_current_org_id)):return {'org':current_scope.get().org_id}
        @app.get('/unscoped')
        def unscoped():return {'org':current_scope.get().org_id}
        with TestClient(app) as client:
            headers={'Authorization':'Bearer '+create_access_token({'sub':'1'})}
            for route in ('/sync','/async'):
                self.assertEqual(client.get(route,headers=headers).json(),{'org':1})
                self.assertEqual(client.get(route,headers=headers|{'X-Org-Id':'2'}).status_code,403)
            self.assertEqual(client.get('/unscoped').json(),{'org':None})
        self.assertIsNone(current_scope.get())

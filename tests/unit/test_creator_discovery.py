"""Source suggestions must contain only canonical, workspace-visible records."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from fastapi import HTTPException
from app.services import creator_discovery as discovery
from app.routes.creator_workspace import post_card, render_creator_workspace
from app.routes.studio import studio_discover_sources
from app.services.text_provider import TextGenerationError


class CreatorDiscoveryTests(unittest.TestCase):
    def test_invalid_briefs_never_call_paid_provider(self):
        for idea, source in [(None, 'quran'), ('  ', 'quran'), ('x'*601, 'quran'), ('patience', 'invented')]:
            with self.subTest(idea=str(idea)[:12]), patch.object(discovery,'generate_text') as provider:
                with self.assertRaises(ValueError): discovery.discover_sources(None, 2, 7, idea, source)
                provider.assert_not_called()

    def test_ai_only_supplies_queries_not_scripture_and_inaccessible_sources_are_skipped(self):
        canonical={'id':3,'reference':'Fixture reference','translation_text':'Exact fixture','arabic_text':'نص'}
        def resolve(db, org, kind, payload, user):
            self.assertEqual((org,user,kind),(2,7,'quran'))
            if payload['id']==1: raise HTTPException(403,'Private')
            return canonical
        with patch.object(discovery,'generate_text',return_value={'terms':['patience','steadfastness']}) as provider, patch('app.services.quran_service.search_quran',return_value=[SimpleNamespace(id=1),SimpleNamespace(id=3)]), patch.object(discovery,'resolve_selected_source',side_effect=resolve):
            result=discovery.discover_sources(None,2,7,'Help someone through a hard week','quran')
        self.assertEqual(result['sources'],[canonical]);self.assertEqual(result['sources'][0]['arabic_text'],'نص')
        self.assertEqual(provider.call_args.kwargs['schema'],discovery.SearchTerms)
        self.assertTrue(provider.call_args.kwargs['utility'])
        self.assertEqual(provider.call_args.kwargs['timeout'],30)

    def test_empty_database_never_substitutes_ai_memory(self):
        with patch.object(discovery,'generate_text',return_value={'terms':['patience']}),patch('app.services.quran_service.search_quran',return_value=[]):
            result=discovery.discover_sources(None,2,7,'Difficult days','quran')
        self.assertEqual(result['sources'],[])

    def test_hadith_search_is_bounded_deduplicated_and_metadata_unchanged(self):
        record={'reference':'Fixture','translation_text':'Full source','grade':None,'narrator':'Returned narrator'}
        with patch.object(discovery,'generate_text',return_value={'terms':['patience','ease']}),patch('app.services.hadith_service.search_hadith_page',create=True,return_value={'items':[record]}) as search:
            result=discovery.discover_sources(None,2,7,'Difficult days','hadith')
        self.assertEqual(search.call_count,2)
        self.assertEqual(search.call_args_list[1].args,('ease',None,6,None))
        self.assertEqual(result['sources'],[record]);self.assertIsNone(result['sources'][0]['grade'])

    def test_provider_failures_expose_recovery_not_provider_details(self):
        with patch.object(discovery,'discover_sources',side_effect=TextGenerationError('provider_error')):
            with self.assertRaises(HTTPException) as caught:studio_discover_sources({'idea':'Patience'},None,2,SimpleNamespace(id=7))
        self.assertEqual(caught.exception.status_code,503);self.assertIn('Your idea is kept',caught.exception.detail)

    def test_generated_extra_fields_cannot_become_a_source(self):
        with patch.object(discovery,'generate_text',return_value={'terms':['mercy'],'translation_text':'AI invented'}),self.assertRaises(ValueError):
            discovery.discover_sources(None,2,7,'A reminder about mercy','quran')

    def test_workspace_markup_escapes_creator_data_and_has_no_publish_side_effect(self):
        post=SimpleNamespace(id=4,flags={},source_reference='<script>bad</script>',topic='',status='publish_unknown',post_format='feed_4_5',caption='" onclick="bad()',scheduled_time=None,media_url='javascript:bad()')
        card=post_card(post)
        self.assertNotIn('<script>',card);self.assertNotIn('javascript:',card)
        self.assertIn('Check publishing outcome',card);self.assertNotIn('approvePost',card)
        output=render_creator_workspace(None,SimpleNamespace(brand_kit={},name='<Workspace>'),[post],None,'you')
        self.assertIn('&lt;Workspace&gt;',output);self.assertIn('No Instagram account connected',output)

from test_security import DatabaseCase
from app.models import Org, User, OrgMember, IGAccount, Post
from app.routes import app_pages
import asyncio

class CreatorWorkspaceRenderingTests(DatabaseCase):
    def setUp(self):
        super().setUp()
        for model in (IGAccount,Post): model.__table__.create(self.engine)
        self.org=Org(id=1,name='Fixture workspace');self.other=Org(id=2,name='Second workspace')
        self.user=User(id=5,email='fixture@example.test',name='Creator',active_org_id=1,is_superadmin=False)
        self.db.add_all([self.org,self.other,self.user,OrgMember(org_id=1,user_id=5,role='owner'),OrgMember(org_id=2,user_id=5,role='owner')])
        self.db.add_all([IGAccount(id=1,org_id=1,name='Current',access_token='test-only',username='current_fixture',ig_user_id='one',active=True),IGAccount(id=2,org_id=2,name='Other',access_token='test-only',username='other_fixture',ig_user_id='two',active=True)])
        self.db.commit()

    def test_home_posts_and_settings_render_with_the_same_workspace_scoped_editor(self):
        for view in ('home','posts','you'):
            with self.subTest(view=view):
                page=asyncio.run(app_pages.app_dashboard_page(self.user,self.db,view))
                self.assertIn('creator-workspace.js',page);self.assertIn('creator-workspace.css',page)
                self.assertIn('current_fixture',page);self.assertNotIn('other_fixture',page)
                self.assertIn('data-workspace="1:5"',page);self.assertNotIn('user-scalable=no',page)
                self.assertIn('aria-label="Main navigation"',page)

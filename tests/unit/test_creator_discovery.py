"""Source suggestions must contain only canonical, workspace-visible records."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch, Mock
from fastapi import HTTPException
from app.services import creator_discovery as discovery
from app.routes.creator_workspace import post_card, render_creator_workspace
from app.routes.studio import studio_discover_sources
from app.services.text_provider import TextGenerationError


class CreatorDiscoveryTests(unittest.TestCase):
    def test_quran_search_rejects_substrings_and_ranks_combined_theme_matches(self):
        from app.services.quran_service import search_quran
        def item(id, wording):
            return SimpleNamespace(id=id, text=wording, title='Search fixture', topics_slugs=[],
                source_id=1, arabic_text='نص اختباري غير قرآني', meta={'surah_number':id,'verse_number':1})
        collision=item(1,'Synthetic fixture about disease and testimony.')
        weak=item(2,'Synthetic fixture about ease.')
        strong=item(3,'Synthetic fixture about ease during hardship.')
        db=Mock();db.query.return_value.filter.return_value.all.return_value=[collision,weak,strong,strong]
        with patch('app.services.quran_service.get_quran_source',return_value=SimpleNamespace(id=1)):
            result=search_quran(db,'ease')
        self.assertEqual([row.id for row in result],[3,2])
        self.assertEqual(strong.text,'Synthetic fixture about ease during hardship.')

    def test_search_preserves_arabic_and_phrase_matching(self):
        from app.services.quran_service import quran_search_score
        item=SimpleNamespace(text='Synthetic fixture: trust in Allah. نص اختباري',title='',topics_slugs=[])
        self.assertGreater(quran_search_score(item,'trust in allah'),0)
        self.assertGreater(quran_search_score(item,'نص'),0)
        self.assertEqual(quran_search_score(item,'rust'),0)

    def test_discovery_considers_all_terms_before_selecting_candidates(self):
        early=[SimpleNamespace(id=i,text='Synthetic fixture: ease.',title='',topics_slugs=[]) for i in range(1,7)]
        stronger=SimpleNamespace(id=7,text='Synthetic fixture: ease hardship patience.',title='',topics_slugs=[])
        def search(db,term,limit):
            self.assertEqual(limit,24)
            return early if term=='ease' else [stronger]
        with patch.object(discovery,'generate_text',side_effect=[{'terms':['ease','patience']},{'indices':[0,1,2]}]), patch('app.services.quran_service.search_quran',side_effect=search) as lookup, patch.object(discovery,'resolve_selected_source',side_effect=lambda db,org,kind,payload,user:{**payload,'translation_text':'Exact fixture'}):
            result=discovery.discover_sources(None,2,7,'Finding ease in a hard week','quran')
        self.assertEqual(lookup.call_count,2)
        self.assertEqual(result['sources'][0]['id'],7)
        self.assertEqual(len(result['sources']),3)

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
        with patch.object(discovery,'generate_text',side_effect=[{'terms':['patience','steadfastness']},{'indices':[0]}]) as provider, patch('app.services.quran_service.search_quran',return_value=[SimpleNamespace(id=1),SimpleNamespace(id=3)]), patch.object(discovery,'resolve_selected_source',side_effect=resolve):
            result=discovery.discover_sources(None,2,7,'Help someone through a hard week','quran')
        self.assertEqual(result['sources'],[canonical]);self.assertEqual(result['sources'][0]['arabic_text'],'نص')
        self.assertEqual(provider.call_args_list[0].kwargs['schema'],discovery.SearchTerms)
        self.assertEqual(provider.call_args_list[1].kwargs['schema'],discovery.CandidateSelection)
        self.assertTrue(provider.call_args.kwargs['utility'])
        self.assertEqual(provider.call_args.kwargs['timeout'],30)

    def test_empty_database_never_substitutes_ai_memory(self):
        with patch.object(discovery,'generate_text',return_value={'terms':['patience']}),patch('app.services.quran_service.search_quran',return_value=[]):
            result=discovery.discover_sources(None,2,7,'Difficult days','quran')
        self.assertEqual(result['sources'],[])

    def test_hadith_search_is_bounded_deduplicated_and_metadata_unchanged(self):
        record={'reference':'Fixture','translation_text':'Full source','grade':None,'narrator':'Returned narrator'}
        with patch.object(discovery,'generate_text',side_effect=[{'terms':['patience','ease']},{'indices':[0]}]),patch('app.services.hadith_service.search_hadith_page',create=True,return_value={'items':[record]}) as search:
            result=discovery.discover_sources(None,2,7,'Difficult days','hadith')
        self.assertEqual(search.call_count,2)
        self.assertEqual(search.call_args_list[1].args,('ease',None,6,None))
        self.assertEqual(result['sources'],[record]);self.assertIsNone(result['sources'][0]['grade'])

    def test_editorial_matching_returns_only_unchanged_supplied_sources(self):
        sources=[{'translation_text':'Full fixture one','arabic_text':'نص','grade':None},
                 {'translation_text':'Full fixture two','arabic_text':'نص ثان','grade':None}]
        with patch.object(discovery,'generate_text',return_value={'indices':[1,1]}):
            selected=discovery.select_candidate_sources('A useful reminder',sources)
        self.assertEqual(selected,[sources[1]]);self.assertIs(selected[0],sources[1])
        with patch.object(discovery,'generate_text',return_value={'indices':[]}):
            self.assertEqual(discovery.select_candidate_sources('Unrelated brief',sources),[])
        for response in ({'indices':[9]}, {'indices':[0],'quotation':'Invented'}, {'indices':[-1]}, {'indices':[0,1,2,3]}):
            with patch.object(discovery,'generate_text',return_value=response),self.assertRaises(ValueError):
                discovery.select_candidate_sources('A useful reminder',sources)

    def test_ai_search_terms_cannot_be_phrases_that_silently_miss_results(self):
        with self.assertRaises(ValueError):
            discovery.SearchTerms.model_validate({'terms':['ease during hardship']})

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

    def test_pinterest_results_are_not_editable_drafts_and_uncertain_results_need_attention(self):
        post=SimpleNamespace(id=4,flags={'media_manifest':{'pages':[{}]},'pinterest_publication':{'status':'unknown'}},source_reference="Qur'an 94:6",topic='',status='drafted',post_format='feed_4_5',card_message={},caption='',scheduled_time=None,media_url='')
        card=post_card(post)
        self.assertIn('View Pinterest result',card);self.assertNotIn('Continue editing',card)
        output=render_creator_workspace(None,SimpleNamespace(brand_kit={},name='Workspace'),[post],None)
        self.assertIn('Needs your attention',output);self.assertEqual(output.count('Check Pinterest outcome'),1)
        post.flags['pinterest_publication']={'status':'published','sandbox':True}
        self.assertIn('Pinterest sandbox test',post_card(post));self.assertNotIn('Published to Pinterest',post_card(post))

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

    def test_unassigned_and_disconnected_drafts_remain_visible_only_in_own_workspace(self):
        self.db.add_all([
            Post(org_id=1, ig_account_id=None, source_reference='Unassigned draft', status='drafted'),
            Post(org_id=2, ig_account_id=None, source_reference='Foreign draft', status='drafted')])
        self.db.commit()
        page = asyncio.run(app_pages.app_dashboard_page(self.user, self.db, 'posts'))
        self.assertIn('Unassigned draft', page)
        self.assertNotIn('Foreign draft', page)
        self.assertIn('Save or export without a connection', page)

class WorkspaceViewStateTests(unittest.TestCase):
    def test_search_keeps_reference_and_topic_and_uncertain_status_is_not_a_draft(self):
        post=SimpleNamespace(id=4,flags={},source_reference="Qur'an 13:28",topic='Remembrance <daily>',status='publish_unknown',post_format='feed_4_5',caption='',scheduled_time=None,media_url='')
        markup=post_card(post)
        self.assertIn('data-post-category="attention"',markup)
        self.assertIn('remembrance &lt;daily&gt;',markup)
        self.assertIn('13:28',markup)

    def test_mobile_plan_uses_local_calendar_dates_and_only_future_scheduled_posts_are_up_next(self):
        from app.routes.creator_workspace import mobile_plan
        from datetime import datetime, timedelta
        from zoneinfo import ZoneInfo
        now=datetime(2026,10,14,10,tzinfo=ZoneInfo('America/Detroit'))
        def post(number,status):
            return SimpleNamespace(id=number,flags={},source_reference='Fixture',topic='',status=status,post_format='feed_4_5',caption='',scheduled_time=now,media_url='')
        output=mobile_plan([post(1,'scheduled'),post(2,'published'),post(3,'scheduled')],{1:now+timedelta(days=1),2:now-timedelta(days=1),3:now-timedelta(hours=1)},now,'America/Detroit')
        self.assertEqual(output.count('data-plan-upcoming="true"'),1)
        self.assertIn('data-plan-date="2026-10-15"',output)
        self.assertIn('Times shown in America/Detroit',output)
        self.assertIn('Instagram schedule',output)

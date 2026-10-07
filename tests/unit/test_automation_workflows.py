"""End-to-end automation services against disposable fixtures, no external effects."""
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import sys
from unittest.mock import patch

from fastapi import HTTPException
from test_security import DatabaseCase
from test_source_integrity import load_isolated_service
from app.config import settings
from app.models import Org, IGAccount, ContentSource, ContentItem, ContentUsage, TopicAutomation, Post
from app.services import automation_runner, post_service, publisher
from app.routes import automations

CDN='https://res.cloudinary.com/test/image/upload/automation-fixture.jpg'


class AutomationWorkflowTests(DatabaseCase):
    def setUp(self):
        super().setUp()
        for model in (Org,IGAccount,ContentSource,ContentItem,ContentUsage,TopicAutomation,Post):
            model.__table__.create(self.engine,checkfirst=True)
        self.db.add(Org(id=1,name='Fixture'))
        self.db.add(IGAccount(id=1,org_id=1,name='Fixture',active=True,ig_user_id='fixture',access_token='fixture'))
        self.db.add(ContentSource(id=1,org_id=None,name='Fixture',source_type='quran_foundation'))
        self.db.add(ContentItem(id=1,org_id=None,source_id=1,item_type='quran',title='Surah 2, Verse 3',text='Synthetic patience fixture, not scripture',arabic_text='نص اختباري',topics=['patience'],meta={'surah_number':2,'verse_number':3}))
        self.db.add(TopicAutomation(id=1,org_id=1,ig_account_id=1,name='Fixture',topic_prompt='patience',enabled=True,image_mode='quote_card',approval_mode='needs_manual_approve',content_provider_scope='all_sources'))
        self.db.commit()
        stack=ExitStack();self.addCleanup(stack.close)
        self.service=load_isolated_service('automation_service')
        stack.enter_context(patch.dict(sys.modules,{'app.services.automation_service':self.service}))
        stack.enter_context(patch.object(settings,'openai_api_key',None))
        stack.enter_context(patch.object(automation_runner,'generate_topic_variations',return_value=['patience']))
        stack.enter_context(patch.object(automation_runner,'validate_source_relevance',return_value={'accepted':True,'reason':'Fixture'}))
        stack.enter_context(patch('app.services.image_card.generate_quote_card',create=True,return_value=CDN))
        stack.enter_context(patch('app.services.llm.generate_card_framing_from_source',return_value={'supporting_text':'Separate fixture reflection'}))
        self.publish=stack.enter_context(patch.object(automation_runner,'publish_saved_post',return_value=SimpleNamespace(ok=True)))

    def test_run_now_cannot_override_manual_approval(self):
        post=automation_runner.run_automation_once(self.db,1,force_publish=True)
        self.assertIsNotNone(post,self.db.get(TopicAutomation,1).last_error)
        self.assertEqual(post.status,'drafted')
        self.publish.assert_not_called()

    def test_run_once_route_respects_plan_policy(self):
        with patch.object(automations,'run_automation',return_value=SimpleNamespace(post=Post(status='drafted'))) as run:
            automations.trigger_automation(1,db=self.db,org_id=1)
        run.assert_called_once_with(self.db,1)

    def test_run_once_rejects_disabled_plan_before_generation(self):
        self.db.get(TopicAutomation,1).enabled=False;self.db.commit()
        with patch.object(automations,'run_automation') as run, self.assertRaises(HTTPException) as caught:
            automations.trigger_automation(1,db=self.db,org_id=1)
        self.assertEqual(caught.exception.status_code,409)
        run.assert_not_called()

    def test_unused_system_source_beats_recent_user_library_sources(self):
        now=datetime.now(timezone.utc)
        for i in range(2,7):
            self.db.add(ContentItem(id=i,org_id=1,source_id=1,item_type='quran',title=f'Surah 2, Verse {i+3}',text='Synthetic patience fixture',arabic_text='نص اختباري',topics=['patience'],meta={'surah_number':2,'verse_number':i+3}))
            self.db.add(ContentUsage(org_id=1,ig_account_id=1,automation_id=1,content_item_id=i,used_at=now))
        self.db.commit()
        post=automation_runner.run_automation_once(self.db,1)
        self.assertIsNotNone(post,self.db.get(TopicAutomation,1).last_error)
        self.assertEqual(post.content_item_id,1)

    def test_hadith_source_card_caption_and_reopen_keep_provider_metadata(self):
        item=self.db.get(ContentItem,1)
        canonical={'source_type':'hadith','collection_key':'bukhari','hadith_number':7,'collection':'Fixture collection','reference':'Fixture collection 7','translation_text':'Synthetic Hadith fixture, not a religious quotation.','arabic_text':'نص اختباري','card_text':'Synthetic Hadith fixture, not a religious quotation.','narrator':'Returned narrator','grade':None,'provider_metadata':{'chapter':{'id':9}}}
        item.item_type='hadith';item.title=canonical['reference'];item.text=canonical['translation_text'];item.arabic_text=canonical['arabic_text'];item.meta=canonical
        self.db.commit()
        with patch.object(settings,'hadith_in_automations_enabled',True), patch('app.services.hadith_service.get_hadith_by_reference',return_value=canonical):
            post=automation_runner.run_automation_once(self.db,1)
        self.assertIsNotNone(post,self.db.get(TopicAutomation,1).last_error)
        self.db.expire_all();post=self.db.get(Post,post.id)
        self.assertEqual(post.status,'drafted')
        self.assertEqual(post.source_text,canonical['translation_text'])
        self.assertEqual(post.card_message['headline'],canonical['card_text'])
        self.assertEqual(post.card_message['hadith_narrator'],canonical['narrator'])
        self.assertIsNone(post.card_message['hadith_grade'])
        self.assertEqual(post.source_metadata['provider_metadata'],canonical['provider_metadata'])
        self.assertIn(canonical['translation_text'],post.caption)
        self.assertIn(canonical['arabic_text'],post.caption)
        self.assertIn(canonical['narrator'],post.caption)
        self.publish.assert_not_called()

    def test_media_failure_never_schedules_or_publishes(self):
        self.db.get(TopicAutomation,1).approval_mode='auto_approve';self.db.commit()
        with patch('app.services.image_card.generate_quote_card',return_value=None):
            post=automation_runner.run_automation_once(self.db,1)
        self.assertEqual(post.status,'failed')
        self.publish.assert_not_called()
        self.assertEqual(self.db.query(ContentUsage).count(),0)

    def test_failed_generation_route_returns_error_instead_of_success(self):
        with patch.object(automations, 'run_automation', return_value=SimpleNamespace(post=Post(status='failed'))), self.assertRaises(HTTPException) as caught:
            automations.trigger_automation(1, db=self.db, org_id=1)
        self.assertEqual(caught.exception.status_code, 422)

    def test_unverifiable_candidate_does_not_hide_another_valid_source(self):
        first = self.db.get(ContentItem, 1)
        second = ContentItem(id=2, org_id=None, source_id=1, item_type='quran', title='Surah 2, Verse 4', text='Synthetic patience fixture two', arabic_text='نص اختباري', topics=['patience'], meta={'surah_number': 2, 'verse_number': 4})
        self.db.add(second); self.db.commit()
        from app.services.source_grounding import resolve_selected_source
        def verify(db, org_id, source_type, payload):
            if str(payload.get('id')) == '1':
                raise ValueError('Fixture source is stale')
            return resolve_selected_source(db, org_id, source_type, payload)
        with patch('app.services.source_grounding.resolve_selected_source', side_effect=verify), patch('app.services.rotation_engine.random.shuffle'):
            post = automation_runner.run_automation_once(self.db, 1)
        self.assertIsNotNone(post, self.db.get(TopicAutomation, 1).last_error)
        self.assertEqual(post.content_item_id, 2)

    def test_unknown_legacy_policy_cannot_schedule_or_publish(self):
        self.db.get(TopicAutomation, 1).approval_mode = 'unknown'; self.db.commit()
        post = automation_runner.run_automation_once(self.db, 1, force_publish=True)
        self.assertIsNotNone(post)
        self.assertEqual(post.status, 'drafted')
        self.assertIsNone(post.scheduled_time)
        self.publish.assert_not_called()

    def test_api_rejects_unknown_approval_policy(self):
        from app.schemas import TopicAutomationCreate, TopicAutomationUpdate
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            TopicAutomationCreate(ig_account_id=1, name='Fixture', topic_prompt='wisdom', approval_mode='unknown')
        with self.assertRaises(ValidationError):
            TopicAutomationUpdate(approval_mode='unknown')

    def test_new_growth_plans_use_shared_cards_without_changing_explicit_legacy_modes(self):
        from app.schemas import TopicAutomationCreate
        for overrides, expected in (({'automation_version': 2}, 'quote_card'),
                                    ({'automation_version': 1}, 'reuse_last_upload'),
                                    ({'automation_version': 2, 'image_mode': 'library_fixed'}, 'library_fixed')):
            payload = TopicAutomationCreate(ig_account_id=1, name='New plan fixture', topic_prompt='patience',
                                            approval_mode='needs_manual_approve', **overrides)
            plan = automations.create_automation(payload, db=self.db, org_id=1)
            self.assertEqual(plan.image_mode, expected)

    def test_ai_framing_common_words_cannot_dilute_the_selected_source_topic(self):
        for i in range(2, 7):
            self.db.add(ContentItem(id=i, org_id=None, source_id=1, item_type='quran',
                                    title=f'Surah 2, Verse {i+3}', text='Synthetic unrelated fixture: those who speak with you.',
                                    arabic_text='نص اختباري', topics=[], meta={'surah_number':2, 'verse_number':i+3}))
        self.db.commit()
        def relevance(topic, text, reference):
            return {'accepted': 'patience' in text, 'reason': 'Fixture topic check'}
        with patch.object(automation_runner, 'generate_topic_variations', return_value=['Setting boundaries while staying patient with someone who repeatedly disappoints you']), \
             patch.object(automation_runner, 'validate_source_relevance', side_effect=relevance), \
             patch('app.services.rotation_engine.random.shuffle', side_effect=lambda items: items.sort(key=lambda item: item.id, reverse=True)):
            post = automation_runner.run_automation_once(self.db, 1)
        self.assertIsNotNone(post, self.db.get(TopicAutomation, 1).last_error)
        self.assertEqual(post.content_item_id, 1)
        self.assertEqual(self.db.query(Post).count(), 1)

    def test_relevance_failure_returns_actionable_error_without_creating_post(self):
        with patch.object(automation_runner, 'validate_source_relevance', return_value={'accepted':False, 'reason':'Fixture'}):
            result = self.service.run_automation(self.db, 1)
        self.assertEqual(result.status, 'no_content')
        self.assertIn('more specific topic', result.error)
        self.assertEqual(self.db.query(Post).count(), 0)
        with patch.object(automations, 'run_automation', return_value=result), self.assertRaises(HTTPException) as caught:
            automations.trigger_automation(1, db=self.db, org_id=1)
        self.assertEqual(caught.exception.status_code, 422)


    def test_feed_quality_rollout_cannot_bypass_creator_review(self):
        self.db.get(TopicAutomation, 1).approval_mode = 'auto_approve'; self.db.commit()
        def render(**kwargs):
            kwargs['render_metadata']['quality'] = {'status': 'passed', 'review_required': True}
            return CDN
        with patch('app.services.image_card.generate_quote_card', side_effect=render):
            post = automation_runner.run_automation_once(self.db, 1, force_publish=True)
        self.assertEqual(post.status, 'drafted')
        self.assertIsNone(post.scheduled_time)
        self.assertTrue(post.flags['visual_review_required'])
        self.publish.assert_not_called()

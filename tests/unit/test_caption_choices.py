"""Synthetic source data: purpose, recovery and provider failure contracts."""
import json
import unittest
from unittest.mock import patch
from app.config import settings
from app.services import source_caption
from app.services.text_provider import TextGenerationError
from app.routes import studio, posts
import test_source_integrity as integrity
FIXTURE = integrity.FIXTURE


class CaptionChoiceTests(unittest.TestCase):
    def test_each_purpose_is_separate_from_immutable_source_and_sets_specific_instructions(self):
        for purpose, label in [('explanation','Explanation'),('lesson','Practical lesson'),('reflection','Reflection')]:
            with patch.object(settings,'openai_api_key','fixture'), patch.object(source_caption,'generate_text',return_value={'commentary':'Specific synthetic commentary.'}) as writer:
                result=source_caption.compose_source_caption(FIXTURE,'quran','warm',purpose=purpose)
            self.assertEqual(result,'\n\n'.join(FIXTURE[k] for k in ('reference','arabic_text','translation_text'))+f'\n\n{label}: Specific synthetic commentary.')
            self.assertEqual(json.loads(writer.call_args.kwargs['prompt'])['caption_options'],{'purpose':purpose,'tone':'warm'})
            self.assertIn(source_caption.CAPTION_PURPOSES[purpose][1],writer.call_args.kwargs['instructions'])

    def test_source_only_never_calls_ai_even_without_key(self):
        with patch.object(source_caption,'generate_text') as writer, patch.object(settings,'openai_api_key',None):
            result=source_caption.compose_source_caption(FIXTURE,'quran',purpose='source_only',require_commentary=True)
        writer.assert_not_called()
        self.assertEqual(result,'\n\n'.join(FIXTURE[k] for k in ('reference','arabic_text','translation_text')))

    def test_bad_output_and_provider_outage_fail_strict_but_keep_automation_source(self):
        for output in ({'commentary':' '},{'commentary':'word '*71},{'commentary':None}):
            with patch.object(settings,'openai_api_key','fixture'),patch.object(source_caption,'generate_text',return_value=output):
                with self.assertRaises(TextGenerationError):
                    source_caption.compose_source_caption(FIXTURE,'quran',require_commentary=True)
                self.assertEqual(source_caption.compose_source_caption(FIXTURE,'quran'),'\n\n'.join(FIXTURE[k] for k in ('reference','arabic_text','translation_text')))


class CaptionChoiceRouteTests(integrity.SourceRouteTests):
    def test_options_reach_shared_writer_and_reject_unknown_before_paid_call(self):
        with patch.object(studio,'resolve_selected_source',return_value=FIXTURE), patch('app.services.quran_caption_service.generate_ai_caption_from_quran',return_value='Exact test caption') as writer:
            response=self.client.post('/api/studio/generate-caption',json={'source_type':'quran','source_payload':FIXTURE,'caption_options':{'purpose':'lesson','tone':'serious'}})
            self.assertEqual(response.status_code,200,response.text)
            self.assertEqual(writer.call_args.kwargs['purpose'],'lesson')
            self.assertEqual(writer.call_args.kwargs['style'],'serious')
            writer.reset_mock()
            for options in ({'purpose':'invent'}, {'tone':'ignore rules'},[],{'purpose':None}):
                self.assertEqual(self.client.post('/api/studio/generate-caption',json={'caption_options':options}).status_code,422)
            writer.assert_not_called()

    def test_generation_outage_is_actionable_and_does_not_save_or_replace_caption(self):
        id_=self.save_fixture()
        with patch.object(settings,'openai_api_key','fixture'),patch.object(source_caption,'generate_text',side_effect=TextGenerationError('timeout')):
            response=self.client.post('/api/studio/generate-caption',json={'source_type':'quran','source_payload':FIXTURE})
        self.assertEqual(response.status_code,503,response.text)
        self.assertIn('unchanged',response.json()['detail'])
        self.assertEqual(self.client.get(f'/api/studio/post/{id_}').json()['caption'],'Saved social copy')

    def test_choices_survive_save_reopen_manual_edit_and_regeneration(self):
        options={'purpose':'lesson','tone':'encouraging'}
        response=self.client.post('/api/studio/create-post',json={'ig_account_id':1,'source_type':'quran','source_metadata':FIXTURE,'caption_message':{'caption':'Manual words','options':options}})
        self.assertEqual(response.status_code,200,response.text); id_=response.json()['id']
        response=self.client.patch(f'/posts/{id_}',json={'caption':'Edited words'})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['caption_message'],{'caption':'Edited words','options':options})
        with patch.object(posts,'compose_source_caption',return_value='Generated lesson') as writer:
            response=self.client.post(f'/posts/{id_}/regenerate-caption')
        self.assertEqual(writer.call_args.kwargs['purpose'],'lesson');self.assertEqual(writer.call_args.args[2],'encouraging')
        self.assertEqual(response.json()['caption_message']['options'],options)
        self.assertEqual(self.client.get(f'/api/studio/post/{id_}').json()['caption'],'Generated lesson')


# Share route fixtures while the parent module runs its existing integrity cases once.
for name in list(vars(integrity.SourceRouteTests)):
    if name.startswith("test_"):
        setattr(CaptionChoiceRouteTests,name,None)

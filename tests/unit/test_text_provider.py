"""Synthetic inputs only; provider/production networking is forbidden by the runner."""
import json
from contextlib import nullcontext
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import httpx
from openai import APIStatusError, APITimeoutError
from app.config import settings
from app.services import text_provider as provider, source_caption, relevance_engine
from test_source_integrity import load_isolated_service, FIXTURE


def response(text='{"reflection":"A separate reflection."}', **changes):
    data = dict(status="completed", output=[], output_text=text, model="fixture-model", usage=SimpleNamespace(output_tokens=12))
    return SimpleNamespace(**{**data, **changes})


class TextProviderTests(unittest.TestCase):
    def setUp(self):
        for stub in (patch("app.services.usage_limits.paid_call", side_effect=lambda kind: nullcontext()), patch.object(settings, "openai_api_key", "fixture")):
            stub.start(); self.addCleanup(stub.stop)

    def call(self, **kwargs):
        return provider.request_text(api_key="fixture-key", model="fixture-model", effort="low", instructions="Fixture instructions", prompt="Fixture prompt", **kwargs)

    def test_schema_request_is_bounded_stateless_and_not_retried(self):
        with patch.object(provider, "OpenAI") as client:
            create = client.return_value.__enter__.return_value.responses.create
            create.return_value = response()
            result = self.call(schema=provider.Reflection)
        self.assertEqual(result, {"reflection": "A separate reflection."})
        client.assert_called_once_with(api_key="fixture-key", timeout=45, max_retries=0)
        kwargs = create.call_args.kwargs
        self.assertEqual(kwargs['reasoning'], {"effort": "low"})
        self.assertFalse(kwargs['store'])
        self.assertEqual(kwargs['max_output_tokens'], 2048)
        self.assertTrue(kwargs['text']['format']['strict'])
        self.assertFalse(kwargs['text']['format']['schema']['additionalProperties'])
        self.assertNotIn('temperature', kwargs)

    def test_rejects_incomplete_refused_empty_and_invalid_schema(self):
        fixtures = [
            (response(status="incomplete"), "incomplete"),
            (response(output=[SimpleNamespace(content=[SimpleNamespace(type="refusal")])]), "refused"),
            (response(text=" "), "empty_output"),
            (response(text='{"reflection":12}'), "invalid_output"),
            (response(text='{"reference":"invented","reflection":"test"}'), "invalid_output"),
            (response(text='[]'), "invalid_output"),
        ]
        for fixture, code in fixtures:
            with self.subTest(code=code), patch.object(provider, "OpenAI") as client:
                client.return_value.__enter__.return_value.responses.create.return_value = fixture
                with self.assertRaises(provider.TextGenerationError) as caught:
                    self.call(schema=provider.Reflection)
                self.assertEqual(caught.exception.code, code)

    def test_provider_errors_never_expose_response_body_or_retry(self):
        request = httpx.Request("POST", "https://api.openai.com/v1/responses")
        for error in [APITimeoutError(request=request), APIStatusError("secret-provider-body", response=httpx.Response(429,request=request),body={"secret":"test"})]:
            with patch.object(provider, "OpenAI") as client:
                create = client.return_value.__enter__.return_value.responses.create
                create.side_effect = error
                with self.assertRaises(provider.TextGenerationError) as caught:
                    self.call()
                self.assertNotIn("secret", str(caught.exception))
                create.assert_called_once()

    def test_writing_and_utility_models_use_separate_configuration(self):
        with patch.object(provider, "request_text", return_value="fixture") as request:
            provider.generate_text("fixture")
            self.assertEqual(request.call_args.kwargs['model'], settings.openai_text_model)
            self.assertEqual(request.call_args.kwargs['effort'], "low")
            provider.generate_text("fixture", utility=True)
            self.assertEqual(request.call_args.kwargs['model'], settings.openai_utility_model)
            self.assertEqual(request.call_args.kwargs['effort'], "none")

    def test_missing_key_never_creates_client(self):
        with patch.object(provider, "OpenAI") as client, self.assertRaises(provider.TextGenerationError):
            provider.request_text(api_key=None, model="fixture", effort="low", instructions="", prompt="")
        client.assert_not_called()

    def test_glow_requires_four_byte_values(self):
        for values in ([12,34,56], [1,2,3,400], [True,2,3,4], [1,2,3,4,5]):
            with patch.object(provider, "OpenAI") as client, self.assertRaises(provider.TextGenerationError):
                client.return_value.__enter__.return_value.responses.create.return_value = response(json.dumps({"glow_color_rgba":values}))
                self.call(schema=provider.Glow)


class TextFlowTests(unittest.TestCase):
    def setUp(self):
        self.llm = load_isolated_service('llm')
        stub = patch('app.services.usage_limits.paid_call', side_effect=lambda kind: nullcontext())
        stub.start(); self.addCleanup(stub.stop)

    def test_no_mock_draft_when_key_missing(self):
        with patch.object(settings, 'openai_api_key', None), self.assertRaises(provider.TextGenerationError):
            self.llm.generate_draft("Synthetic topic")

    def test_draft_never_accepts_generated_religious_attribution(self):
        output = {"caption":"Fixture reflection", "source":"Invented religious attribution"}
        with patch.object(self.llm, 'generate_text', return_value=output):
            result = self.llm.generate_draft('Fixture')
        self.assertEqual(result['source'], 'General Reflection')

    def test_rewrite_cannot_ask_model_to_find_scripture(self):
        for kind in ('ayah', 'hadith'):
            with patch.object(self.llm, 'generate_text') as generate, self.assertRaises(ValueError):
                self.llm.refine_caption('Fixture',kind)
            generate.assert_not_called()

    def test_rewrite_failure_is_not_reported_as_success(self):
        with patch.object(self.llm, 'generate_text', side_effect=provider.TextGenerationError('timeout')), self.assertRaises(provider.TextGenerationError):
            self.llm.refine_caption('Original fixture', 'shorter')

    def test_topic_variations_have_deterministic_failure_recovery(self):
        with patch.object(settings, 'openai_api_key', 'fixture'), patch.object(self.llm, 'generate_text', side_effect=provider.TextGenerationError('refused')):
            self.assertEqual(len(self.llm.generate_topic_variations('Fixture',3)),3)

    def test_card_framing_preserves_reference_and_no_fake_fallback(self):
        with patch.object(settings, 'openai_api_key', 'fixture'), patch.object(self.llm, 'generate_text', return_value={'supporting_text':'Separate reflection', 'eyebrow':'Wrong'}):
            result = self.llm.generate_card_framing_from_source('Fixture','wisdom','calm','','quran','Exact reference')
        self.assertEqual(result['eyebrow'],'Exact reference')
        with patch.object(settings, 'openai_api_key', None):
            result = self.llm.generate_card_framing_from_source('Fixture','wisdom','calm','','quran','Exact reference')
        self.assertEqual(result, {'eyebrow':'Exact reference','supporting_text':''})

    def test_sacred_library_caption_uses_same_exact_source_assembly(self):
        with patch.object(settings,'openai_api_key','fixture'), patch.object(source_caption,'generate_text',return_value={'reflection':'Separate reflection'}), patch.object(self.llm,'generate_text') as generic:
            result = self.llm.generate_topic_caption('fixture', extra_context={'snippet':{'item_type':'quran','text':FIXTURE['translation_text'],'reference':FIXTURE['reference'],'arabic_text':FIXTURE['arabic_text']}})
        self.assertIn(FIXTURE['translation_text'],result['caption'])
        self.assertIn(FIXTURE['arabic_text'],result['caption'])
        generic.assert_not_called()

    def test_overlong_optional_reflection_is_omitted_without_cutting_source(self):
        with patch.object(settings,'openai_api_key','fixture'), patch.object(source_caption,'generate_text',return_value={'reflection':'word '*51}):
            caption = source_caption.compose_source_caption(FIXTURE,'quran','calm')
        self.assertEqual(caption,'\n\n'.join(FIXTURE[k] for k in ('reference','arabic_text','translation_text')))

    def test_relevance_fails_closed_on_outage_or_low_confidence(self):
        with patch.object(relevance_engine,'generate_text',side_effect=provider.TextGenerationError('not_configured')):
            self.assertFalse(relevance_engine.validate_source_relevance('Fixture','Fixture')['accepted'])
        with patch.object(relevance_engine,'generate_text',return_value={'accepted':True,'confidence':'low','reason':'Fixture'}):
            self.assertFalse(relevance_engine.validate_source_relevance('Fixture','Fixture')['accepted'])

    def test_refine_endpoint_returns_actionable_errors(self):
        from app.routes import app_pages
        from app.services import llm as routed_llm
        from fastapi import HTTPException
        with patch.object(routed_llm, 'refine_caption', self.llm.refine_caption, create=True):
            with self.assertRaises(HTTPException) as caught:
                app_pages.api_refine_content(app_pages.RefineRequest(text='Fixture',type='ayah'),user=object())
            self.assertEqual(caught.exception.status_code,422)
            with patch.object(self.llm,'generate_text',side_effect=provider.TextGenerationError('timeout')), self.assertRaises(HTTPException) as caught:
                app_pages.api_refine_content(app_pages.RefineRequest(text='Fixture',type='shorter'),user=object())
            self.assertEqual(caught.exception.status_code,503)

    def test_actual_provider_output_is_assembled_with_exact_source(self):
        with patch.object(settings,'openai_api_key','fixture'), patch.object(provider,'OpenAI') as client:
            client.return_value.__enter__.return_value.responses.create.return_value = response()
            caption = source_caption.compose_source_caption(FIXTURE,'quran','calm')
        self.assertEqual(caption,'\n\n'.join(FIXTURE[k] for k in ('reference','arabic_text','translation_text'))+'\n\nReflection: A separate reflection.')

    def test_incompatible_reasoning_configuration_is_rejected(self):
        from app.config import Settings
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            Settings(openai_text_model='gpt-6-astra',openai_text_reasoning_effort='none')

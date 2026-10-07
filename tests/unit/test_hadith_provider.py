"""Collection identity regressions with synthetic narration fixtures only."""
from copy import deepcopy
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
from app.config import settings
from test_source_integrity import load_isolated_service

RECORD = {'id': 1, 'metadata': {'volume': {'id': 2}, 'chapter': {'id': 3}},
          'language': {'ar': {'text': 'نص اختباري'}, 'en': {'text': 'Synthetic intentions fixture.', 'narrator': 'Returned narrator'}}}


class HadithProviderTests(unittest.TestCase):
    def setUp(self):
        self.service = load_isolated_service('hadith_service')

    def test_search_and_cold_reference_lookup_use_same_collection_record(self):
        def provider(url, **kwargs):
            if '/hadith?' not in url:
                self.fail('Inconsistent single-record endpoint must never be used')
            return [deepcopy(RECORD)]
        with patch.object(settings, 'hadith_api_key', 'fixture'), patch.object(self.service, '_get_json', side_effect=provider):
            found = self.service.search_hadith('intentions', 'bukhari')
            resolved = self.service.get_hadith_by_reference('bukhari', 1)
        self.assertEqual(found, [resolved])
        self.assertEqual(resolved['translation_text'], RECORD['language']['en']['text'])
        self.assertEqual(resolved['arabic_text'], RECORD['language']['ar']['text'])
        self.assertEqual(resolved['narrator'], RECORD['language']['en']['narrator'])
        self.assertEqual(resolved['provider_metadata'], RECORD['metadata'])
        self.assertIsNone(resolved['grade'])

    def test_page_hint_is_not_assumed_to_be_record_identity(self):
        target = {**deepcopy(RECORD), 'id': 123}
        def provider(url, **kwargs):
            page = parse_qs(urlsplit(url).query)['page'][0]
            return [target] if page == '1' else [deepcopy(RECORD)]
        with patch.object(self.service, '_get_json', side_effect=provider) as fetch:
            resolved = self.service._sunnah_now_get_hadith_by_reference('muslim', 123)
        self.assertEqual(resolved['hadith_number'], 123)
        self.assertEqual(resolved['collection_key'], 'muslim')
        self.assertEqual(fetch.call_count, 1)

    def test_missing_wrong_duplicate_or_malformed_records_fail_closed(self):
        for response in ([], [deepcopy(RECORD)], {'id': 2}, [None], [dict(RECORD, id=2), dict(RECORD, id=2)]):
            with self.subTest(response=response), patch.object(self.service, '_get_json', return_value=response) as fetch:
                self.assertIsNone(self.service._sunnah_now_get_hadith_by_reference('bukhari', 2))
                self.assertLessEqual(fetch.call_count, 3)
        for number in (0, -1, True, 1.5, None):
            with patch.object(self.service, '_get_json') as fetch:
                self.assertIsNone(self.service._sunnah_now_get_hadith_by_reference('bukhari', number))
                fetch.assert_not_called()

    def test_normalization_rejects_missing_identity_and_preserves_returned_grade(self):
        self.assertIsNone(self.service._normalize_sunnah_now_hadith({**RECORD, 'id': None}, 'bukhari'))
        actual = self.service._normalize_sunnah_now_hadith({**RECORD, 'grade': 'Provider fixture grade'}, 'bukhari')
        self.assertEqual(actual['grade'], 'Provider fixture grade')

    def test_search_continues_beyond_150_and_revalidates_nonsequential_identity(self):
        filler = [{**deepcopy(RECORD), 'id': n, 'language': {'en': {'text': 'Other synthetic text.'}}} for n in range(50)]
        target = {**deepcopy(RECORD), 'id': 9999}
        def page(key, number):
            return filler if number <= 3 else [target] if number == 4 else []
        with patch.object(settings, 'hadith_api_key', 'fixture'), patch.object(self.service, '_sunnah_now_collection_page', side_effect=page):
            first = self.service.search_hadith_page('intentions', 'bukhari')
            self.assertEqual(first['items'], [])
            self.assertFalse(first['complete'])
            self.assertEqual(first['pages_scanned'], 3)
            second = self.service.search_hadith_page('intentions', 'bukhari', cursor=first['next_cursor'])
            item = second['items'][0]
            self.assertTrue(second['complete'])
            self.assertEqual(item['provider_page'], 4)
            resolved = self.service.get_hadith_by_reference('bukhari', 9999, provider_page=item['provider_page'])
            self.assertEqual(resolved, item)
            self.assertIsNone(self.service.get_hadith_by_reference('bukhari', 1, provider_page=4))

    def test_page_offsets_do_not_skip_remaining_matches(self):
        records = [{**deepcopy(RECORD), 'id': n+1} for n in range(50)]
        with patch.object(settings, 'hadith_api_key', 'fixture'), patch.object(self.service, '_sunnah_now_collection_page', side_effect=lambda key, page: records if page == 1 else []):
            first = self.service.search_hadith_page('intentions', 'bukhari', limit=30)
            second = self.service.search_hadith_page('intentions', 'bukhari', limit=30, cursor=first['next_cursor'])
        self.assertEqual([x['hadith_number'] for x in first['items'] + second['items']], list(range(1, 51)))
        self.assertTrue(second['complete'])

    def test_provider_failure_is_not_reported_as_empty_or_complete(self):
        with patch.object(settings, 'hadith_api_key', 'fixture'), patch.object(self.service, '_sunnah_now_collection_page', return_value=None):
            with self.assertRaises(RuntimeError):
                self.service.search_hadith_page('intentions')

    def test_cursor_is_bound_to_query_and_validated_before_network(self):
        with patch.object(settings, 'hadith_api_key', 'fixture'), patch.object(self.service, '_sunnah_now_collection_page', return_value=[{**deepcopy(RECORD), 'id': n} for n in range(50)]):
            first = self.service.search_hadith_page('intentions', 'bukhari')
        with patch.object(settings, 'hadith_api_key', 'fixture'), patch.object(self.service, '_sunnah_now_collection_page') as fetch:
            for cursor in ('garbage', 'W10', first['next_cursor']):
                with self.assertRaises(ValueError):
                    self.service.search_hadith_page('different', 'bukhari', cursor=cursor)
            fetch.assert_not_called()

    def test_search_route_reports_provider_failure_as_retryable_http_error(self):
        from app.routes.library import search_hadith_library
        from fastapi import HTTPException
        with patch('app.services.hadith_service.search_hadith_page', create=True, side_effect=RuntimeError('private provider diagnostic')):
            with self.assertRaises(HTTPException) as caught:
                search_hadith_library('fixture', user=object())
        self.assertEqual(caught.exception.status_code, 503)
        self.assertNotIn('private', caught.exception.detail)

    def test_source_resolution_rechecks_search_page_and_rejects_wrong_identity(self):
        from app.services.source_grounding import resolve_selected_source
        canonical = self.service._normalize_sunnah_now_hadith(RECORD, 'bukhari')
        payload = {**canonical, 'provider_page': 4}
        with patch('app.services.hadith_service.get_hadith_by_reference', return_value=canonical) as fetch:
            self.assertEqual(resolve_selected_source(None, 1, 'hadith', payload), canonical)
            fetch.assert_called_once_with('bukhari', 1, provider_page=4)
        with patch('app.services.hadith_service.get_hadith_by_reference', return_value={**canonical, 'hadith_number': 2}):
            with self.assertRaisesRegex(ValueError, 'different source'):
                resolve_selected_source(None, 1, 'hadith', payload)

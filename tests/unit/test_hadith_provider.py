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

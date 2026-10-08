"""Synthetic text verifies editorial note separation; never scripture fixtures."""
import copy
import unittest
from app.services.quran_translation import parse_translation, verified_translation_repair
from app.services.quran_serialization import normalize_quran_verse
from app.services.source_grounding import validate_saved_source_snapshot
from types import SimpleNamespace

RAW='Synthetic body with 12 days.<sup foot_note="99">1</sup> [An inline clarification].'
TRANSLATION={'verse_key':'2:3','resource_id':20,'resource_name':'Returned translator','text':RAW,'foot_notes':{'99':'<p>Returned note</p>'}}
ITEM={'title':'Surah 2, Verse 3','text':'Synthetic body with 12 days.1 [An inline clarification].','arabic_text':'نص اختباري', 'meta':{'verse_key':'2:3','translation_id':'131'}}

class QuranAnnotationTests(unittest.TestCase):
    def test_separates_only_identified_note_markers(self):
        out=parse_translation(TRANSLATION)
        self.assertEqual(out['body'],'Synthetic body with 12 days. [An inline clarification].')
        self.assertEqual(out['raw_html'],RAW)
        self.assertEqual(out['footnotes'][0]['text'],'Returned note')
        plain={**TRANSLATION,'text':'Preserve 12 and word.1 [2] exactly.'}
        self.assertEqual(parse_translation(plain)['body'],plain['text'])

    def test_unknown_superscripts_and_bad_notes_fail_without_guessing(self):
        for changed in ({'text':'Body<sup>2</sup>'},{'foot_notes':{'99':{'unexpected':'object'}}},{'text':'<script>bad</script>'}):
            with self.assertRaises(ValueError):parse_translation({**TRANSLATION,**changed})

    def test_empty_notes_remain_explicitly_unavailable(self):
        out=parse_translation({**TRANSLATION,'foot_notes':{'99':''}})
        self.assertIsNone(out['footnotes'][0]['text'])
        self.assertEqual(out['footnotes'][0]['status'],'unavailable')

    def test_repair_is_exact_identity_bound_and_idempotent(self):
        out=verified_translation_repair(ITEM,TRANSLATION,ITEM['arabic_text'],{'author_name':'Returned author'})
        self.assertEqual(out['meta']['translation_id'],'20')
        self.assertEqual(out['meta']['translation_correction']['previous_translation_id'],'131')
        self.assertEqual(out,verified_translation_repair({**ITEM,**out},TRANSLATION,ITEM['arabic_text'],{'author_name':'Returned author'}))
        for changed in ({'text':'Different words'},{'arabic_text':'مختلف'},{'title':'Surah 2, Verse 4'},{'meta':{'verse_key':'2:4'}}):
            with self.assertRaises(ValueError):verified_translation_repair({**ITEM,**changed},TRANSLATION,ITEM['arabic_text'],{})

    def test_normalized_source_exposes_notes_and_rejects_tampered_body(self):
        out=verified_translation_repair(ITEM,TRANSLATION,ITEM['arabic_text'],{'author_name':'Returned author'})
        record=normalize_quran_verse({**ITEM,**out})
        self.assertEqual(record['translation_text'],out['text'])
        self.assertEqual(record['translation_footnotes'][0]['text'],'Returned note')
        self.assertEqual(record['translator'],'Returned author')
        self.assertEqual(record['translation_provenance']['raw_html'],RAW)
        with self.assertRaises(ValueError):normalize_quran_verse({**ITEM,**out,'text':'Tampered body'})

    def test_historical_saved_source_snapshot_is_not_rewritten(self):
        source=normalize_quran_verse(ITEM)
        card={'eyebrow':source['reference'],'headline':source['translation_text'],'arabic_text':source['arabic_text']}
        post=SimpleNamespace(source_type='quran',source_metadata=source,source_reference=source['reference'],source_text=source['translation_text'],card_message=card)
        before=copy.deepcopy(post.__dict__)
        validate_saved_source_snapshot(post)
        self.assertEqual(post.__dict__,before)

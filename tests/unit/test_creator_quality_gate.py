"""Release decisions must not mistake engineering evidence for human review."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts.evaluate_creator_quality import (
    FAMILIES, FORMATS, SOURCE_KEYS, artifact_digest, check_painted_source,
    check_source_coverage, digest, release_decision, verify_artifacts,
)


def complete_rows():
    return [{'id':f'{source}_{family}_{fmt}', 'automated_status':'passed',
             'artifact_digest':digest([source,family,fmt]), 'pages':[{'fixture':True}], 'errors':[]}
            for source in sorted(SOURCE_KEYS) for family in FAMILIES for fmt in FORMATS]


def declarations(rows):
    # Synthetic test evidence only; never written to a real review bundle.
    return {row['id']:{'artifact_digest':row['artifact_digest'],
        'creator':{'reviewer':'Synthetic fixture', 'date':'2026-01-01', 'usable_without_repair':True},
        'qualified_source':{'reviewer':'Synthetic fixture', 'date':'2026-01-01', 'approved':True}}
        for row in rows}


class CreatorQualityGateTests(unittest.TestCase):
    def test_engineering_success_never_manufactures_human_approval(self):
        result=release_decision(complete_rows())
        self.assertTrue(result['matrix_complete'])
        self.assertEqual(result['automated_passed'],36)
        self.assertFalse(result['release_ready'])
        self.assertEqual(result['creator_reviewed'],0)
        self.assertEqual(result['qualified_source_approved'],0)
        self.assertTrue(result['manual_review_required'])

    def test_missing_or_duplicate_cases_do_not_complete_matrix(self):
        rows=complete_rows()
        for bad in (rows[:-1],rows[:-1]+[rows[0]],rows+[rows[0]]):
            self.assertFalse(release_decision(bad,declarations(bad))['release_ready'])

    def test_changed_artifact_invalidates_earlier_human_review(self):
        rows=complete_rows(); reviews=declarations(rows)
        self.assertTrue(release_decision(rows,reviews)['release_ready'])
        rows[0]['artifact_digest']=digest('changed pixels')
        result=release_decision(rows,reviews)
        self.assertFalse(result['release_ready'])
        self.assertEqual(result['creator_reviewed'],35)

    def test_ninety_percent_usable_and_all_source_reviews_required(self):
        rows=complete_rows(); reviews=declarations(rows)
        for row in rows[:3]: reviews[row['id']]['creator']['usable_without_repair']=False
        self.assertTrue(release_decision(rows,reviews)['release_ready'])
        reviews[rows[3]['id']]['creator']['usable_without_repair']=False
        self.assertFalse(release_decision(rows,reviews)['release_ready'])
        reviews=declarations(rows); reviews[rows[0]['id']]['qualified_source']['approved']=False
        self.assertFalse(release_decision(rows,reviews)['release_ready'])

    def test_automated_errors_or_missing_images_cannot_be_overruled(self):
        rows=complete_rows(); reviews=declarations(rows)
        for changes in ({'automated_status':'blocked'},{'errors':['glyph']},{'pages':[]}):
            bad=copy.deepcopy(rows); bad[0].update(changes)
            self.assertFalse(release_decision(bad,reviews)['release_ready'])

    def test_coverage_rejects_omitted_arabic_overlap_and_unknown_roles(self):
        card={'headline':'Exact source', 'arabic_text':'نص تجريبي'}
        manifest={'pages':[{'slices':[{'role':'source_translation','start':0,'end':12},
                                     {'role':'source_arabic','start':0,'end':9}]}]}
        self.assertEqual(check_source_coverage(card,manifest),[])
        for mutation in ('omit','overlap','unknown'):
            bad=copy.deepcopy(manifest)
            if mutation=='omit': bad['pages'][0]['slices'].pop()
            elif mutation=='overlap': bad['pages'].append(bad['pages'][0])
            else: bad['pages'][0]['slices'].append({'role':'invented','start':0,'end':1})
            self.assertTrue(check_source_coverage(card,bad))

    def test_painted_words_checked_against_slices_not_only_manifest(self):
        card={'headline':'Exact source', 'supporting_text':'Separate reflection'}
        page={'slices':[{'role':'source_translation','start':0,'end':12},
                        {'role':'reflection','start':0,'end':19}]}
        audits=[{'role':'source_translation','lines':['Exact','source']},
                {'role':'reflection','lines':['Separate reflection']}]
        self.assertEqual(check_painted_source(card,page,audits),[])
        audits[0]['lines']=['Rewritten source']
        self.assertTrue(check_painted_source(card,page,audits))

    def test_saved_image_changes_invalidate_bundle(self):
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp); file=directory/'card.jpg'; file.write_bytes(b'fixture image')
            row={'id':'fixture','source_sha256':digest('source'),'card':{},'family':'editorial','format':'feed_4_5',
                 'pages':[{'file':'card.jpg','sha256':hashlib.sha256(file.read_bytes()).hexdigest()}]}
            row['artifact_digest']=artifact_digest(row)
            self.assertEqual(verify_artifacts([row],directory),[])
            file.write_bytes(b'edited image')
            self.assertTrue(verify_artifacts([row],directory))
            file.unlink()
            self.assertTrue(verify_artifacts([row],directory))

    def test_committed_source_snapshots_have_intact_provenance_digests(self):
        sources=json.loads((Path(__file__).resolve().parents[1]/'quality/sources.json').read_text())
        self.assertEqual({s['key'] for s in sources},SOURCE_KEYS)
        self.assertEqual(len(sources),6)
        for source in sources:
            self.assertEqual(digest(source['record']),source['record_sha256'])
            self.assertTrue(source['record']['arabic_text'])
            self.assertTrue(source['record']['translation_text'])

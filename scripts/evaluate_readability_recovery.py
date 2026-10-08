"""Replay real photographs through the canonical renderer without paid calls.

Preserves exact source snapshots. All output stays outside the repository; no
database, application, scheduler, uploads or network are allowed in this runner.
"""
import argparse
import contextlib
import io
import json
import os
from pathlib import Path
import socket
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def run(backgrounds, output):
    output.mkdir(parents=True, exist_ok=True)
    os.chdir(output)
    os.environ['SECRET_KEY'] = 'isolated-readability-recovery-evaluation'
    sys.path[:0] = [str(ROOT), str(ROOT/'scripts')]
    from PIL import Image
    from app.config import settings
    from app.services import image_card, image_renderer
    from app.services.brand_kit import normalize_brand
    from app.services.quote_message_service import build_quote_card_message
    from app.services.source_grounding import validate_source_card
    from evaluate_creator_quality import digest, check_source_coverage, check_painted_source
    sources = json.loads((ROOT/'tests/quality/sources.json').read_text())
    sources = {s['key']: s for s in sources}
    short = sources['quran_short']
    cases = []
    for path in sorted(backgrounds.glob('*.json')):
        row = json.loads(path.read_text())
        if row.get('background') and row.get('family') and row.get('id'):
            cases.append(dict(id=row['id'], source=short, background=backgrounds/row['background'],
                              family=row['family'], format=row['format'], previous_status=row['status'],
                              identity=row.get('visual_identity','')))
    integrated = backgrounds.parent/'2026-10-08-vision-families/live-integrated'
    for family in ('luxury_editorial', 'desert_glow', 'midnight_oasis', 'emerald_forest'):
        for fmt in ('feed_4_5', 'story_9_16'):
            bg = integrated/f'{family}_{fmt}.png'
            if not bg.is_file():
                raise ValueError('Missing explicit background: '+str(bg))
            for key in ('quran_medium', 'hadith_medium') if family != 'emerald_forest' else ('quran_medium',):
                cases.append(dict(id=f'{family}_{fmt}_{key}',source=sources[key],background=bg,
                                  family=family,format=fmt,previous_status='not_evaluated'))
    # Optional explicitly captured production incident: exact canonical records
    # plus the three raw photographs linked from that incident's runtime logs.
    captured = output/'production-sources.json'
    if captured.is_file():
        for source in json.loads(captured.read_text()):
            for family in ('luxury_editorial', 'desert_glow', 'midnight_oasis'):
                bg = output/f'reported_{family}_raw.jpg'
                for fmt in ('feed_4_5', 'story_9_16'):
                    cases.append(dict(id=f'reported_{family}_{source["key"]}_{fmt}',source=source,
                                      background=bg,family=family,format=fmt,previous_status='reported_rejection'))
    rows = []
    def forbidden(*a, **k):
        raise RuntimeError('Network is forbidden in this replay')
    for case in cases:
        saved = output/(case['id']+'.json')
        if saved.is_file():
            rows.append(json.loads(saved.read_text()))
            continue
        source = case['source']
        assert digest(source['record']) == source['record_sha256']
        with contextlib.redirect_stdout(io.StringIO()):
            card = build_quote_card_message(source['type'], source['record'], include_reflection=False)
        validate_source_card(card, source['record'], source['type'])
        brand = normalize_brand({'family':case['family'],'signature':'@sabeel_studio',
            'series_name':'A moment to reflect','visual_identity':case.get('identity','')})
        row = {k:v for k,v in case.items() if k not in {'source','background'}}
        row.update(source_key=source['key'], reference=source['record']['reference'],
                   source_sha256=source['record_sha256'], background=str(case['background']),
                   pages=[], errors=[], creator_review=None, qualified_source_review=None)
        audits=[]; metadata={}; started=time.monotonic()
        original=image_renderer.paint_card_text
        def paint(bg, blocks, **kwargs):
            result=original(bg, blocks, **kwargs)
            audits.append([{'role':b['role'],'lines':[l['text'] for l in b['lines']]} for b in blocks])
            return result
        def save(filename, local_path):
            target=output/(case['id']+f'_{len(row["pages"])+1:02}.jpg')
            Path(local_path).replace(target)
            row['pages'].append({'file':target.name,'audit':audits[-1]})
            return str(target)
        try:
            with patch.object(socket,'create_connection',side_effect=forbidden), \
                 patch.object(socket.socket,'connect',side_effect=forbidden), \
                 patch.object(image_renderer,'generate_background',side_effect=forbidden), \
                 patch.object(image_renderer,'paint_card_text',side_effect=paint), \
                 patch.object(settings,'uploads_dir',str(output)), \
                 patch('app.config.build_public_media_url',side_effect=save), \
                 contextlib.redirect_stdout(io.StringIO()):
                image_card.generate_quote_card(card_message=card, style=case['family'], post_format=case['format'],
                    brand_kit=brand, allow_sequence=True, background_image=Image.open(case['background']).convert('RGB'),
                    render_metadata=metadata)
            row['errors'] += check_source_coverage(card,metadata['media_manifest'])
            for page,manifest in zip(row['pages'],metadata['media_manifest']['pages']):
                page['quality']=manifest['quality']
                row['errors'] += check_painted_source(card,manifest,page['audit'])
            row['status']='passed' if not row['errors'] else 'failed'
        except ValueError as error:
            row.update(status='rejected', errors=[str(error)])
        row['seconds']=round(time.monotonic()-started,2)
        rows.append(row)
        (output/(case['id']+'.json')).write_text(json.dumps(row,ensure_ascii=False,indent=2)+'\n')
        print(case['id'],row['status'],row['seconds'],flush=True)
    (output/'results.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
    assert 'app.main' not in sys.modules and 'app.db' not in sys.modules


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--backgrounds',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path)
    args=p.parse_args()
    if args.output.resolve().is_relative_to(ROOT):
        raise SystemExit('Output must be outside the repository')
    run(args.backgrounds.resolve(),args.output.resolve())

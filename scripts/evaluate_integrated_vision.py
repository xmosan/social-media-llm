"""Offline regression through the actual card/renderer pipeline and saved AI plates.

No credentials, application startup, database, uploads, generation or publishing.
Pass directories containing the recorded pilot/refined experiments. Every case
checks the complete source manifest and delivered JPEG, including rejected cases.
"""
import argparse
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'scripts'))


def run(output, inputs):
    output.mkdir(parents=True, exist_ok=True)
    os.chdir(output)
    os.environ['SECRET_KEY'] = 'isolated-integrated-vision-only-0001'
    from PIL import Image
    from app.config import settings
    from app.services import image_card, image_renderer
    from app.services.quote_message_service import build_quote_card_message
    from app.services.source_grounding import validate_source_card
    from app.services.brand_kit import normalize_brand
    from evaluate_creator_quality import digest, check_source_coverage, check_painted_source
    sources = json.loads((ROOT/'tests/quality/sources.json').read_text())
    rows = []
    def forbidden(*args, **kwargs):
        raise AssertionError('Network is forbidden in this offline evaluation')
    for directory in inputs:
        for record_path in sorted(directory.glob('*_feed_4_5.json'))+sorted(directory.glob('*_story_9_16.json')):
            record = json.loads(record_path.read_text())
            if record.get('status') != 'success' and not record.get('background'):
                continue
            raw_path = directory/(record.get('file') or record['background'])
            if hashlib.sha256(raw_path.read_bytes()).hexdigest() != (record.get('sha256') or record['background_sha256']):
                raise ValueError('Background artifact changed')
            raw = Image.open(raw_path).convert('RGB')
            for source in sources:
                if digest(source['record']) != source['record_sha256']:
                    raise ValueError('Source snapshot changed')
                identity = directory.name+'_'+record['id']+'_'+source['key']
                row = {'id':identity, 'family':record['family'], 'format':record['format'],
                       'source_key':source['key'], 'reference':source['record']['reference'],
                       'source_sha256':source['record_sha256'], 'background':str(raw_path),
                       'pages':[], 'errors':[], 'creator_review':None, 'qualified_source_review':None}
                with contextlib.redirect_stdout(io.StringIO()):
                    card = build_quote_card_message(source['type'], source['record'], include_reflection=False)
                validate_source_card(card, source['record'], source['type'])
                brand = normalize_brand({'palette':'olive','typography':'modern','signature':'@sabeel_studio',
                                         'series_name':'A moment to reflect','family':record['family']})
                metadata, audits = {}, []
                original_paint = image_renderer.paint_card_text
                def paint(background, blocks, **kwargs):
                    audits.append([{'role':b['role'], 'lines':[line['text'] for line in b['lines']],
                                    'font_size':b['size'], 'bounds':b['bounds']} for b in blocks])
                    return original_paint(background, blocks, **kwargs)
                def save(filename, local_path):
                    index = len(row['pages'])
                    target = output/f'{identity}_{index+1:02}.jpg'
                    Path(local_path).replace(target)
                    row['pages'].append({'file':target.name, 'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
                                         'audit':audits[-1]})
                    return str(target)
                retained = []
                with patch.object(socket.socket,'connect',forbidden), patch.object(socket,'create_connection',forbidden), \
                     patch.object(settings,'uploads_dir',str(output)), patch.object(image_renderer,'generate_background',return_value=raw.copy()) as provider, \
                     patch.object(image_renderer,'paint_card_text',side_effect=paint), patch('app.config.build_public_media_url',side_effect=save), \
                     contextlib.redirect_stdout(io.StringIO()):
                    try:
                        image_card.generate_quote_card(card_message=card, style=record['family'], post_format=record['format'],
                            allow_sequence=True, brand_kit=brand, render_metadata=metadata,
                            background_sink=lambda image:retained.append(image.size))
                        row['errors'].extend(check_source_coverage(card, metadata['media_manifest']))
                        for page, item in zip(row['pages'],metadata['media_manifest']['pages']):
                            page['quality'] = item['quality']
                            row['errors'].extend(check_painted_source(card,item,page['audit']))
                        row['status'] = 'rejected' if row['errors'] else 'automated_pass'
                        if provider.call_count != 1:
                            raise AssertionError('Sequence must reuse one background')
                    except ValueError as error:
                        row['status'] = 'rejected' if provider.call_count else 'blocked'
                        row['errors'].append(str(error))
                row['background_calls'] = provider.call_count
                row['raw_retained'] = bool(retained)
                rows.append(row)
                (output/'evaluation.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
                print(identity, row['status'], len(row['pages']), flush=True)
    assert 'app.main' not in sys.modules and 'app.db' not in sys.modules
    from collections import Counter
    summary = {'cases':len(rows),'statuses':dict(Counter(r['status'] for r in rows)),
        'families':{f:dict(Counter(r['status'] for r in rows if r['family']==f)) for f in sorted({r['family'] for r in rows})},
        'delivered_pages':sum(len(r['pages']) for r in rows), 'new_provider_requests':0,
        'external_reviews':0,'release_gate':'manual_review_required'}
    (output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary),flush=True)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('inputs',type=Path,nargs='+')
    args=parser.parse_args()
    if args.output.resolve().is_relative_to(ROOT):
        raise SystemExit('Keep generated assets outside the repository')
    run(args.output.resolve(),[p.resolve() for p in args.inputs])

"""Offline, reproducible creator-quality matrix using the canonical renderer.

No app startup, database, scheduler, upload, or paid calls. Photographs must be
provided explicitly. Successful engineering checks never imply human approval.
"""
import argparse
import contextlib
from collections import Counter
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import sys
import unicodedata
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
FAMILIES = ("editorial", "quiet_photography", "minimal_paper")
FORMATS = ("feed_4_5", "story_9_16")
SOURCE_KEYS = {f"{kind}_{length}" for kind in ("quran", "hadith") for length in ("short", "medium", "long")}


def artifact_digest(row):
    return digest({'source':row['source_sha256'], 'card':row['card'],
        'files':[p['sha256'] for p in row['pages']], 'family':row['family'], 'format':row['format']})


def verify_artifacts(rows, directory):
    """Fail closed if a reviewed file changed, disappeared, or left its bundle."""
    errors = []
    directory = directory.resolve()
    for row in rows:
        if not row.get('pages') or row.get('artifact_digest') != artifact_digest(row):
            errors.append(f"{row['id']}: missing pages or changed artifact digest")
        for page in row.get('pages', []):
            path = (directory / page['file']).resolve()
            if path.parent != directory or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != page['sha256']:
                errors.append(f"{row['id']}: missing or changed image")
    return errors


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def check_source_coverage(card, manifest):
    errors = []
    allowed = {'source_translation', 'source_arabic', 'reflection'}
    if any(part.get('role') not in allowed for page in manifest.get('pages', []) for part in page.get('slices', [])):
        errors.append('Unknown source slice role')
    for role, field in (("source_translation", "headline"), ("source_arabic", "arabic_text"), ("reflection", "supporting_text")):
        text, cursor = card.get(field) or "", 0
        for page in manifest.get("pages", []):
            for part in page.get("slices", []):
                if part.get("role") != role:
                    continue
                start, end = part.get("start"), part.get("end")
                if type(start) is not int or type(end) is not int or start != cursor or not start < end <= len(text):
                    errors.append(f"{role}: noncontiguous source")
                    continue
                cursor = end
        if cursor != len(text):
            errors.append(f"{role}: incomplete source")
    return errors


def check_painted_source(card, page, audits):
    fields = {'source_translation':'headline', 'source_arabic':'arabic_text', 'reflection':'supporting_text'}
    compact = lambda text: ''.join(text.split())
    expected = {role: ''.join((card.get(field) or '')[part['start']:part['end']]
        for part in page['slices'] if part['role'] == role) for role,field in fields.items()}
    painted = {role: ''.join(''.join(a['lines']) for a in audits if a['role']==role) for role in fields}
    narration = ''.join(''.join(a['lines']) for a in audits if a['role']=='narration_context')
    errors = []
    # In the identified Hadith layout narration and message are separate blocks.
    # Page-level codepoint coverage remains exact; slice checks retain ordering.
    if narration:
        expected_source = compact(expected['source_translation']+expected['source_arabic'])
        painted_source = compact(painted['source_translation']+painted['source_arabic']+narration)
        if Counter(expected_source) != Counter(painted_source):
            errors.append('Painted narration/source differs from canonical slices')
    else:
        for role in ('source_translation','source_arabic'):
            if compact(expected[role]) != compact(painted[role]):
                errors.append(f'Painted {role} differs from canonical slices')
    if compact(expected['reflection']) != compact(painted['reflection']):
        errors.append('Painted reflection differs from its own separate field')
    return errors


def release_decision(rows, human_reviews=None):
    """Human assessments are external evidence tied to exact artifact digests.

    This runner only consumes declarations; it cannot verify a reviewer's identity
    or qualifications. The generated report never creates these declarations.
    """
    expected = {f"{source}_{family}_{fmt}" for source in SOURCE_KEYS for family in FAMILIES for fmt in FORMATS}
    complete = len(rows) == 36 and {r['id'] for r in rows} == expected
    hard_pass = sum(r.get('automated_status') == 'passed' and not r.get('errors') and bool(r.get('pages')) for r in rows)
    human_reviews = human_reviews or {}
    creator_reviewed = creator_usable = source_reviewed = 0
    for row in rows:
        evidence = human_reviews.get(row['id']) or {}
        if not row.get('artifact_digest') or evidence.get('artifact_digest') != row['artifact_digest']:
            continue
        creator = evidence.get('creator') or {}
        source = evidence.get('qualified_source') or {}
        if creator.get('reviewer') and creator.get('date') and type(creator.get('usable_without_repair')) is bool:
            creator_reviewed += 1
            creator_usable += creator['usable_without_repair']
        if source.get('reviewer') and source.get('date') and source.get('approved') is True:
            source_reviewed += 1
    return {'matrix_complete': complete, 'automated_passed': hard_pass, 'matrix_cases': len(rows),
        'creator_reviewed': creator_reviewed, 'creator_usable_without_repair': creator_usable,
        'qualified_source_approved': source_reviewed,
        'release_ready': bool(complete and hard_pass == 36 and creator_reviewed == 36 and
                              creator_usable / 36 >= .9 and source_reviewed == 36),
        'manual_review_required': True}


def run(sources_path, backgrounds, output, shared_background=None):
    # Explicitly prevent accidental .env loading from a checkout.
    os.chdir(output)
    os.environ['SECRET_KEY'] = 'isolated-creator-quality-evaluation-only'
    sys.path.insert(0, str(ROOT))
    sources = json.loads(sources_path.read_text())
    if len(sources) != 6 or {s['key'] for s in sources} != SOURCE_KEYS:
        raise ValueError('Provide exactly the six declared source-length cases')
    for source in sources:
        if digest(source['record']) != source['record_sha256']:
            raise ValueError('Source snapshot digest changed')
    from PIL import Image
    from fontTools.ttLib import TTFont
    import numpy as np
    from app.config import settings
    from app.services import image_renderer, card_typography
    from app.services.image_card import generate_quote_card
    from app.services.quote_message_service import build_quote_card_message
    from app.services.brand_kit import normalize_brand
    from app.services.source_grounding import validate_source_card

    def forbidden(*a, **k):
        raise RuntimeError('Network/startup is forbidden in this quality evaluation')

    glyphs = {}
    for file in (card_typography.ARABIC_FONT, card_typography.LATIN_FONT):
        with TTFont(file, fontNumber=0) as font:
            glyphs[str(file)] = set(font.getBestCmap())

    def luminance(rgb):
        rgb = rgb / 255
        linear = np.where(rgb <= .04045, rgb / 12.92, ((rgb + .055) / 1.055) ** 2.4)
        return linear @ np.array([.2126, .7152, .0722])

    rows = []
    for source in sources:
        record = source['record']
        with contextlib.redirect_stdout(io.StringIO()):
            card = build_quote_card_message(source['type'], record, include_reflection=False)
        validate_source_card(card, record, source['type'])
        for family in FAMILIES:
            for fmt in FORMATS:
                identity = f"{source['key']}_{family}_{fmt}"
                row = {'id': identity, 'source_key': source['key'], 'reference': record['reference'],
                    'family': family, 'format': fmt, 'source_sha256': source['record_sha256'],
                    'card': card, 'pages': [], 'errors': [], 'agent_visual_assessment': None,
                    'human_creator_review': None, 'qualified_source_review': None}
                captures, metadata = [], {}
                original_paint = image_renderer.paint_card_text
                def capture(background, blocks, **kwargs):
                    rendered = original_paint(background, blocks, **kwargs)
                    quality = kwargs['quality']
                    amount = quality['wash_opacity']
                    backing = Image.blend(background.convert('RGB'), Image.new('RGB', background.size, (248,246,239)), amount) if amount else background.convert('RGB')
                    audits = []
                    for block in blocks:
                        mask = card_typography._ink_mask(background.size, block, 'Left')
                        fontpath = str(block['font'].path)
                        text = ''.join(line['text'] for line in block['lines'])
                        missing = sorted({ord(c) for c in text if not c.isspace() and unicodedata.category(c) != 'Cf' and ord(c) not in glyphs[fontpath]})
                        label = block.get('label')
                        if label:
                            missing += sorted({ord(c) for c in label['text'] if not c.isspace() and ord(c) not in glyphs[str(label['font'].path)]})
                        audits.append({'role': block['role'], 'font_size': block['size'], 'font_320': round(block['size']*320/1080,2),
                            'font_390': round(block['size']*390/1080,2), 'bounds': list(block['bounds']),
                            'ink_bounds': mask.getbbox(), 'missing_codepoints': missing,
                            'lines': [line['text'] for line in block['lines']],
                            'label': label['text'] if label else None, '_mask': mask})
                    captures.append((backing, audits))
                    return rendered
                brand = normalize_brand({'palette':'olive','typography':'modern','signature':'@sabeel_studio',
                    'series_name':'A moment to reflect','family':family})
                try:
                    photo_path = shared_background or (backgrounds / f"{source['key']}.png")
                    photo = Image.open(photo_path).convert('RGB') if family == 'quiet_photography' else None
                    with patch.object(socket.socket,'connect',forbidden), patch.object(socket,'create_connection',forbidden), \
                         patch.object(settings,'uploads_dir',str(output)), \
                         patch('app.config.build_public_media_url',side_effect=lambda filename,local_path:local_path), \
                         patch.object(image_renderer,'paint_card_text',side_effect=capture), contextlib.redirect_stdout(io.StringIO()):
                        generate_quote_card(card_message=card,style=family,layout='english_first',mode='scene',
                            allow_sequence=True,post_format=fmt,render_metadata=metadata,brand_kit=brand,background_image=photo)
                    manifest = metadata['media_manifest']
                    validate_source_card(card, record, source['type'])
                    if digest(record) != source['record_sha256']:
                        row['errors'].append('Canonical source changed during rendering')
                    row['errors'].extend(check_source_coverage(card, manifest))
                    row['brand'] = brand
                    row['photograph'] = str(photo_path) if photo else None
                    row['photograph_sha256'] = hashlib.sha256(photo_path.read_bytes()).hexdigest() if photo else None
                    for i, page in enumerate(manifest['pages']):
                        filename = f"{identity}_{i+1:02d}.jpg"
                        path = output / filename
                        Path(page['url']).replace(path)
                        image = Image.open(path).convert('RGB')
                        backing, audits = captures[i]
                        row['errors'].extend(f'page {i+1}: {error}' for error in check_painted_source(card,page,audits))
                        pixels, bg_pixels = np.asarray(image), np.asarray(backing)
                        for audit in audits:
                            ink = np.asarray(audit.pop('_mask')) >= 250
                            fg, bg = luminance(pixels[ink].astype(float)), luminance(bg_pixels[ink].astype(float))
                            ratios = (np.maximum(fg,bg)+.05)/(np.minimum(fg,bg)+.05)
                            audit['jpeg_minimum_contrast'] = round(float(ratios.min()),3) if len(ratios) else 0
                            bounds = audit['ink_bounds']
                            frame = audit['bounds']
                            if bounds is None or min(bounds[0],frame[0])<0 or min(bounds[1],frame[1])<(250 if fmt=='story_9_16' else 0) or max(bounds[2],frame[2])>1080 or max(bounds[3],frame[3])>(1610 if fmt=='story_9_16' else 1350):
                                row['errors'].append(f"page {i+1}: ink outside safe area")
                            if any(line and unicodedata.category(line[0]).startswith('M') for line in audit['lines']):
                                row['errors'].append(f"page {i+1}: detached combining mark at line start")
                            if audit['missing_codepoints']:
                                row['errors'].append(f"page {i+1}: missing glyphs")
                            if audit['jpeg_minimum_contrast'] < 4.5:
                                row['errors'].append(f"page {i+1}: final JPEG contrast below 4.5")
                        if image.size != (1080,1920 if fmt=='story_9_16' else 1350):
                            row['errors'].append(f"page {i+1}: incorrect dimensions")
                        row['pages'].append({**{k:v for k,v in page.items() if k!='url'},'file':filename,
                            'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'audit':audits})
                    row['automated_status'] = 'failed' if row['errors'] else 'passed'
                except Exception as error:
                    row['automated_status'] = 'blocked'
                    row['errors'].append(str(error))
                row['artifact_digest'] = artifact_digest(row)
                rows.append(row)
                (output/'evaluation.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
                print(json.dumps({'id':identity,'status':row['automated_status'],'pages':len(row['pages']),'errors':row['errors']}),flush=True)
    (output/'release-gate.json').write_text(json.dumps(release_decision(rows),indent=2)+'\n')
    assert 'app.main' not in sys.modules and 'app.services.scheduler' not in sys.modules
    return rows


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sources',type=Path,default=ROOT/'tests/quality/sources.json')
    parser.add_argument('--backgrounds',type=Path)
    parser.add_argument('--shared-background',type=Path,help='Explicit typography-only replay; no photography diversity claim')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--assess',action='store_true',help='Verify an existing output bundle; exit 1 unless the release gate passes')
    parser.add_argument('--human-reviews',type=Path,help='Externally completed reviews, keyed by case id and exact artifact digest')
    args=parser.parse_args()
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    if args.assess:
        rows=json.loads((output/'evaluation.json').read_text())
        reviews=json.loads(args.human_reviews.read_text()) if args.human_reviews else None
        decision=release_decision(rows,reviews)
        decision['artifact_errors']=verify_artifacts(rows,output)
        decision['release_ready'] &= not decision['artifact_errors']
        (output/'release-gate.json').write_text(json.dumps(decision,indent=2)+'\n')
        print(json.dumps(decision,indent=2))
        raise SystemExit(0 if decision['release_ready'] else 1)
    if not args.backgrounds:
        parser.error('--backgrounds is required when rendering')
    run(args.sources.resolve(),args.backgrounds.resolve(),output,args.shared_background.resolve() if args.shared_background else None)

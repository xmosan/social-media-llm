"""Bounded live background experiment and offline canonical card evaluation.

The experiment does not enable families in production. Generation requires
--live and an explicit env file; reruns never repeat an attempted paid request.
Rendering imports no application/database/scheduler, uploads or publishes nothing.
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
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))

BRIEFS = {
    'luxury_editorial': [
        'An ordinary warm plaster wall in a modest well-lit home, with a small fold of natural ivory linen resting on a limestone ledge at the very bottom right. Real material imperfections, soft overcast window light, cream and muted olive undertones. A candid interior photograph, not a product render.',
        'A close study of a gently weathered pale limestone interior wall, with a plain wooden table edge and a small folded cotton cloth at the lower left. Soft reflected daylight, tactile but very fine surface texture, warm grey and chalk tones. Believable home interior photography, no decorative props.'
    ],
    'desert_glow': [
        'Quiet low dunes photographed just before sunrise, the distant dune ridge in the bottom fifth and a large pale dust-blue and warm cream sky. Restrained natural colour, fine realistic sand and subdued shadows. Documentary landscape photography, not a fantasy desert or a movie poster.',
        'An open desert plain in soft early daylight, a low distant ridge at the bottom fifth, muted sand and warm grey sky. A small wind-shaped dune at the lower right adds believable depth. Gentle light, restrained saturation and realistic atmospheric perspective.'
    ],
    'midnight_oasis': [
        'A modest limestone courtyard at blue hour. A plain deep indigo plaster wall occupies most of the frame; a single believable recessed doorway sits low at the far right. Soft reflected dusk light with subtle texture. No visible moon, stars, lamps or dramatic light beams. Natural architectural photograph.',
        'A quiet domestic terrace at early dusk, an uninterrupted dark slate-blue sky and softly lit ordinary stone parapet low in the frame. A subtle wall return at the far left provides depth. Restrained true photographic shadows and believable geometry, no dramatic arches or palatial decoration.'
    ],
}
FORMATS = {'feed_4_5': ('1088x1360', (1080, 1350)), 'story_9_16': ('1152x2048', (1080, 1920))}
REFINED_BRIEFS = {
    'luxury_editorial': ['A believable interior photograph of a smooth warm ivory plaster wall. Fine subtle texture, soft diffuse overcast light and consistently light tones throughout the reading area. A low pale wooden ledge with a small fold of natural linen only below the reading area. No plants, vases, branches, dramatic shadows, coarse stone, dark edges or decorative objects. Material detail should feel photographic, softly imperfect and ordinary rather than glossy or computer-rendered.'],
    'midnight_oasis': ['A believable outdoor architectural photograph at late blue hour. An uninterrupted evenly dark navy sky above a low plain stone courtyard wall. No trees, plants, lights, lanterns, stars, doorways, bright stone edges or objects extending into the reading area. Subtle realistic atmosphere, quiet true photographic exposure. The low wall and a small amount of terrace floor below the reading area provide credible depth.'],
    'emerald_forest': ['A real-looking still lake on an overcast morning with a low distant tree line and muted sage-grey atmosphere. The reading area is open pale sky and softly reflected water with no contrasting branches, objects or hard horizon crossing it. A narrow band of realistic reeds and a distant soft tree line remain below the reading area. Believable nature photography, diffuse light, restrained color, no supernatural mist, dramatic rays or fantasy.'],
}


def configure(output, env_file=None):
    os.chdir(output)
    os.environ['SECRET_KEY'] = 'isolated-vision-evaluation-only-0001'
    if env_file:
        from dotenv import dotenv_values
        values = dotenv_values(env_file)
        os.environ['OPENAI_API_KEY'] = values.get('OPENAI_API_KEY') or ''
    from PIL import features
    if not features.check_feature('raqm'):
        raise RuntimeError('RAQM is required for exact Arabic shaping')


def compact_scene_blocks(blocks, post_format):
    """Experiment: keep source attribution together, freeing the scene foreground.

    Only coordinates change. Fonts, shaping, source order and exact text survive.
    """
    result = [dict(block) for block in blocks]
    series = next((b for b in result if b['role']=='series_title'), None)
    body = [b for b in result if b['role'] not in {'series_title','reference','creator_signature'}]
    footer = [b for role in ('reference','creator_signature') for b in result if b['role']==role]
    y = series['bounds'][3]+48 if series else min(b['bounds'][1] for b in body)
    gap = 28 if any(b['role']=='narration_context' for b in body) else 38
    for block in body:
        left,_,right,_=block['bounds']
        block.update(y=y,bounds=(left,y,right,y+block['height']))
        y += block['height']+gap
    y += 26
    for block in footer:
        left,_,right,_=block['bounds']
        block.update(y=y,bounds=(left,y,right,y+block['height']))
        y += block['height']+24
    if max(b['bounds'][3] for b in result) > (1610 if post_format=='story_9_16' else 1270):
        return blocks
    return result


def cards_and_plans(compact=False, balanced=False):
    from app.services import image_card
    from app.services.card_typography import layout_card
    from app.services.quote_message_service import build_quote_card_message
    from app.services.source_grounding import validate_source_card
    from app.services.brand_kit import normalize_brand
    from evaluate_creator_quality import digest
    sources = json.loads((ROOT / 'tests/quality/sources.json').read_text())
    plans = {}
    for source in sources:
        if digest(source['record']) != source['record_sha256']:
            raise ValueError('Source snapshot changed')
        with contextlib.redirect_stdout(io.StringIO()):
            card = build_quote_card_message(source['type'], source['record'], include_reflection=False)
        validate_source_card(card, source['record'], source['type'])
        brand = normalize_brand({'palette': 'olive', 'typography': 'modern', 'signature': '@sabeel_studio',
                                 'series_name': 'A moment to reflect', 'family': 'editorial'})
        for fmt in FORMATS:
            pages, metadata = [], {}
            def capture(segments, *args, **kwargs):
                if balanced and any(len(s['text']) > (80 if s['role']=='source_arabic' else 100) for s in segments):
                    # Use the existing, tested continuation reading scale; never
                    # shrink beneath it or change a single canonical character.
                    segments = [dict(s, sequence_page=True) for s in segments]
                size, blocks = layout_card(segments, family='editorial', layout='english_first', post_format=fmt, brand_kit=brand)
                if compact or balanced:
                    blocks = compact_scene_blocks(blocks, fmt)
                pages.append({'segments': segments, 'size': size, 'blocks': blocks})
                return 'isolated-page'
            try:
                with patch.object(image_card, 'render_minimal_quote_card', side_effect=capture), contextlib.redirect_stdout(io.StringIO()):
                    image_card.generate_quote_card(card_message=card, style='editorial', post_format=fmt,
                        allow_sequence=True, brand_kit=brand, render_metadata=metadata)
                plans[(source['key'], fmt)] = {'source': source, 'card': card, 'brand': brand,
                    'pages': pages, 'manifest': metadata['media_manifest']}
            except ValueError as error:
                plans[(source['key'], fmt)] = {'source': source, 'card': card, 'brand': brand, 'blocked': str(error)}
    return plans


def prompt_for(family, variant, fmt, plan, briefs=BRIEFS, refined=False):
    width, height = FORMATS[fmt][1]
    zones = [tuple(round(v / (width if i % 2 == 0 else height) * 100) for i, v in enumerate(b['bounds']))
             for b in plan['pages'][0]['blocks']]
    bottom = max(z[3] for z in zones)
    refinement = (f' The complete reading area runs from 5% down to {min(95,bottom+3)}% of the image height, across the middle 86% of its width. '
        'It must have a single consistent lightness: '+('evenly dark' if family=='midnight_oasis' else 'evenly pale')+'. '
        f'Confine the foreground scene to below {min(95,bottom+3)}% height. Do not place any object in the reading area. ') if refined else ''
    return (briefs[family][variant] + refinement + f' Portrait {"4:5 feed" if fmt=="feed_4_5" else "9:16 Story"} composition. '
        'This is a background for exact typography added separately. Maintain a continuous natural scene, '
        'with low-detail evenly lit areas under the following text rectangles (left, top, right, bottom, percentages): '
        + str(zones) + '. Keep major objects and strong edges away from these areas, including the small bottom reference. '
        'Do not draw rectangles, panels, borders or empty label boxes. No lettering, pseudo-script, Arabic, symbols, logos, '
        'people, sacred-site reconstructions, supernatural imagery, glow, gold decoration, excessive blur or glossy CGI. '
        'Preserve photographic depth and realistic materials. No text anywhere.')


def generate(output, plans, refined=False):
    from app.services.image_provider import generate_configured_image, ImageGenerationError
    from app.config import settings
    briefs = REFINED_BRIEFS if refined else BRIEFS
    for family in briefs:
        for variant in range(len(briefs[family])):
            for fmt, (size, _) in FORMATS.items():
                identity = f'{family}_{variant+1}_{fmt}'
                record_path = output / f'{identity}.json'
                if record_path.exists():
                    print(identity + ' already attempted; not charged again', flush=True)
                    continue
                prompt = prompt_for(family, variant, fmt, plans[('quran_medium', fmt)],briefs,refined)
                record = {'id': identity, 'family': family, 'variant': variant+1, 'format': fmt,
                    'prompt': prompt, 'requested_size': size, 'quality': settings.openai_image_quality,
                    'model': settings.openai_image_model, 'status': 'started', 'started_at': time.time()}
                record_path.write_text(json.dumps(record, indent=2)+'\n')
                print(identity + ' started', flush=True)
                start = time.monotonic()
                try:
                    result = generate_configured_image(prompt, engine='openai', size=size)
                    file = output / f'{identity}.png'
                    result.image.save(file)
                    record.update(status='success', file=file.name, model=result.model, usage=result.usage,
                        actual_size=list(result.image.size), sha256=hashlib.sha256(file.read_bytes()).hexdigest())
                except ImageGenerationError as error:
                    record.update(status='failed', code=error.code, http_status=error.status)
                record['seconds'] = round(time.monotonic()-start, 2)
                record_path.write_text(json.dumps(record, indent=2)+'\n')
                print(json.dumps({k:record[k] for k in ('id','status','seconds')}), flush=True)
                if record.get('http_status') in {401,402,403,404,429}:
                    return


def render(output, plans, strong_ink=False):
    import numpy as np
    from PIL import Image, ImageOps
    from app.services.card_typography import paint_card_text, _ink_mask
    from evaluate_creator_quality import check_source_coverage, check_painted_source
    results = []
    def luminance(rgb):
        rgb = rgb / 255
        return np.where(rgb <= .04045, rgb/12.92, ((rgb+.055)/1.055)**2.4) @ np.array([.2126,.7152,.0722])
    def forbidden(*args, **kwargs):
        raise RuntimeError('Network forbidden during offline rendering')
    for record_file in sorted(output.glob('*_feed_4_5.json')) + sorted(output.glob('*_story_9_16.json')):
        record = json.loads(record_file.read_text())
        if record['status'] != 'success':
            continue
        with Image.open(output / record['file']) as im:
            raw = im.convert('RGB')
        for source_key in ('quran_short','quran_medium','hadith_short','hadith_medium','quran_long','hadith_long'):
            plan = plans[(source_key, record['format'])]
            row = {'id':record['id']+'_'+source_key, 'background':record['file'], 'family':record['family'],
                   'variant':record['variant'], 'format':record['format'], 'source_key':source_key,
                   'reference':plan['source']['record']['reference'], 'source_sha256':plan['source']['record_sha256'],
                   'pages':[], 'errors':[], 'creator_review':None, 'qualified_source_review':None}
            if plan.get('blocked'):
                row.update(status='blocked', errors=[plan['blocked']])
                results.append(row)
                continue
            row['errors'].extend(check_source_coverage(plan['card'], plan['manifest']))
            with patch.object(socket.socket, 'connect', forbidden), patch.object(socket, 'create_connection', forbidden):
                for i, page in enumerate(plan['pages']):
                    background = ImageOps.fit(raw, page['size'], method=Image.Resampling.LANCZOS)
                    quality = {}
                    try:
                        image = paint_card_text(background, page['blocks'], quality=quality, brand_kit=plan['brand'], wash_limit=.2, strong_ink=strong_ink)
                    except ValueError as error:
                        row['errors'].append(f'page {i+1}: {error}')
                        break
                    name = f"{row['id']}_{i+1:02}.jpg"
                    image.save(output/name, quality=95)
                    backing = Image.blend(background, Image.new('RGB',page['size'],(248,246,239)),quality['wash_opacity'])
                    pixels = np.asarray(Image.open(output/name).convert('RGB'))
                    bg = np.asarray(backing)
                    audits = []
                    for block in page['blocks']:
                        mask = np.asarray(_ink_mask(page['size'],block,'Left')) >= 250
                        fg, under = luminance(pixels[mask].astype(float)), luminance(bg[mask].astype(float))
                        score = float(((np.maximum(fg,under)+.05)/(np.minimum(fg,under)+.05)).min())
                        audits.append({'role':block['role'], 'lines':[l['text'] for l in block['lines']],
                            'font_size':block['size'], 'bounds':list(block['bounds']), 'jpeg_minimum_contrast':round(score,3)})
                        if score < 4.5:
                            row['errors'].append(f'page {i+1}: final JPEG contrast below 4.5')
                    row['errors'].extend(check_painted_source(plan['card'],plan['manifest']['pages'][i],audits))
                    row['pages'].append({'file':name, 'sha256':hashlib.sha256((output/name).read_bytes()).hexdigest(),
                        'quality':quality,'audit':audits})
            row['status'] = 'rejected' if row['errors'] else 'automated_pass'
            results.append(row)
            (output/'evaluation.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
            print(json.dumps({k:row[k] for k in ('id','status','errors')}),flush=True)
    (output/'evaluation.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
    assert 'app.main' not in sys.modules and 'app.db' not in sys.modules and 'app.services.scheduler' not in sys.modules


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--env-file',type=Path)
    parser.add_argument('--live',action='store_true')
    parser.add_argument('--render',action='store_true')
    parser.add_argument('--compact',action='store_true',help='Offline attribution placement experiment; no new generation')
    parser.add_argument('--balanced',action='store_true',help='Offline layout uses the established 67px English/57px Arabic continuation scale for medium sources')
    parser.add_argument('--refined',action='store_true',help='Six bounded follow-up backgrounds: revised material/night and two nature challengers')
    args=parser.parse_args()
    output=args.output.resolve()
    if output == ROOT or ROOT in output.parents:
        parser.error('Keep generated artifacts outside the repository')
    if args.live and not args.env_file:
        parser.error('--live requires an explicit --env-file')
    output.mkdir(parents=True,exist_ok=True)
    configure(output,args.env_file)
    if (args.compact or args.balanced) and args.live:
        parser.error('The compact comparison reuses the same backgrounds; do not generate again')
    plans=cards_and_plans(compact=args.compact,balanced=args.balanced or args.refined)
    if args.live:
        generate(output,plans,refined=args.refined)
    if args.render:
        render(output,plans,strong_ink=args.balanced or args.refined)
    if not args.live and not args.render:
        briefs = REFINED_BRIEFS if args.refined else BRIEFS
        print(json.dumps({'planned_requests':sum(len(v) for v in briefs.values())*len(FORMATS),'families':list(briefs),'formats':list(FORMATS)}))

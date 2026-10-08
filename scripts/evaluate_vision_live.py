"""Eight bounded live end-to-end scene checks with verified Qur'an 2:153.

Runs the real provider, planner and renderer. Uploads are replaced with local
artifacts. No app startup, database, scheduler or publishing. Attempts are recorded
before generation and never repeated by this script, even after an interruption.
"""
import argparse
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import time
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))


def run(output,env_file):
    output.mkdir(parents=True,exist_ok=True);os.chdir(output)
    from dotenv import dotenv_values
    os.environ['SECRET_KEY']='isolated-live-vision-validation-0001'
    os.environ['OPENAI_API_KEY']=dotenv_values(env_file).get('OPENAI_API_KEY') or ''
    from app.config import settings
    from app.services import image_card,image_renderer
    from app.services.quote_message_service import build_quote_card_message
    from app.services.source_grounding import validate_source_card
    from app.services.brand_kit import normalize_brand
    from app.services.vision_families import SCENE_FAMILIES
    from app.services.image_provider import ImageGenerationError
    from evaluate_creator_quality import digest,check_source_coverage,check_painted_source
    source=next(s for s in json.loads((ROOT/'tests/quality/sources.json').read_text()) if s['key']=='quran_medium')
    if digest(source['record'])!=source['record_sha256']:raise ValueError('Changed source snapshot')
    with contextlib.redirect_stdout(io.StringIO()):
        card=build_quote_card_message(source['type'],source['record'],include_reflection=False)
    validate_source_card(card,source['record'],source['type'])
    for family in SCENE_FAMILIES:
        for fmt in ('feed_4_5','story_9_16'):
            identity=family+'_'+fmt;record_path=output/(identity+'.json')
            if record_path.exists():continue
            row={'id':identity,'family':family,'format':fmt,'source_key':source['key'],'source_sha256':source['record_sha256'],
                 'status':'started','started_at':time.time(),'pages':[],'creator_review':None,'qualified_source_review':None}
            record_path.write_text(json.dumps(row,indent=2)+'\n')
            start=time.monotonic();metadata={};audits=[]
            brand=normalize_brand({'family':family,'signature':'@sabeel_studio','series_name':'A moment to reflect'})
            original_provider=image_renderer.generate_configured_image
            original_paint=image_renderer.paint_card_text
            def provider(prompt,**kwargs):
                row.update(prompt=prompt,requested_size=kwargs.get('size'),model=settings.openai_image_model,quality=settings.openai_image_quality)
                record_path.write_text(json.dumps(row,indent=2)+'\n')
                result=original_provider(prompt,**kwargs)
                file=output/(identity+'.png');result.image.save(file)
                row.update(background=file.name,background_sha256=hashlib.sha256(file.read_bytes()).hexdigest(),
                    model=result.model,usage=result.usage,generation_seconds=round(time.monotonic()-start,2))
                record_path.write_text(json.dumps(row,indent=2)+'\n')
                return result
            def paint(bg,blocks,**kwargs):
                audits.append([{'role':b['role'],'lines':[line['text'] for line in b['lines']], 'font_size':b['size'],'bounds':b['bounds']} for b in blocks])
                return original_paint(bg,blocks,**kwargs)
            def save(filename,local_path):
                target=output/(identity+f'_{len(row["pages"])+1:02}.jpg');Path(local_path).replace(target)
                row['pages'].append({'file':target.name,'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'audit':audits[-1]})
                return str(target)
            try:
                with patch.object(image_renderer,'generate_configured_image',side_effect=provider), \
                     patch.object(image_renderer,'paint_card_text',side_effect=paint), \
                     patch.object(settings,'uploads_dir',str(output)),patch('app.config.build_public_media_url',side_effect=save),contextlib.redirect_stdout(io.StringIO()):
                    image_card.generate_quote_card(card_message=card,style=family,post_format=fmt,brand_kit=brand,
                        allow_sequence=True,render_metadata=metadata)
                errors=check_source_coverage(card,metadata['media_manifest'])
                for page,item in zip(row['pages'],metadata['media_manifest']['pages']):
                    page['quality']=item['quality'];errors.extend(check_painted_source(card,item,page['audit']))
                row.update(status='rejected' if errors else 'automated_pass',errors=errors,metadata=metadata)
            except (ValueError,ImageGenerationError) as error:
                row.update(status='rejected',errors=[str(error)])
                if isinstance(error,ImageGenerationError):row['http_status']=error.status
            row['seconds']=round(time.monotonic()-start,2)
            record_path.write_text(json.dumps(row,ensure_ascii=False,indent=2)+'\n')
            print(identity,row['status'],row['seconds'],flush=True)
            if row.get('http_status') in {401,402,403,404,429}:return
    assert 'app.main' not in sys.modules and 'app.db' not in sys.modules


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path);parser.add_argument('--env-file',required=True,type=Path)
    args=parser.parse_args()
    if args.output.resolve().is_relative_to(ROOT):raise SystemExit('Keep output outside repository')
    run(args.output.resolve(),args.env_file.resolve())

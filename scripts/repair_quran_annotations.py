"""Audited, offline-evidence repair of global Quran translation imports.

Supply provider JSON from Quran Foundation /quran/translations/<resource> (with
fields=verse_key,resource_name&foot_notes=true) and /quran/verses/uthmani.
DATABASE_URL is read from the environment only. Default is a read-only dry run.
--apply requires a NEW --backup path; rollback uses that same file and checks
that no later edit would be overwritten. No post or user record is touched.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.services.quran_translation import verified_translation_repair


def fingerprint(row):
    return hashlib.sha256(json.dumps(row, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def run(args):
    url = make_url(os.environ['DATABASE_URL'])
    if not url.drivername.startswith('postgresql'):
        raise ValueError('This repair requires PostgreSQL')
    engine = create_engine(url.set(drivername='postgresql+psycopg'), connect_args={
        'options': '-c statement_timeout=30000' + ('' if args.apply else ' -c default_transaction_read_only=on')})
    try:
        with engine.begin() as db:
            if args.rollback:
                saved = json.loads(Path(args.rollback).read_text())
                if saved.get('version') != 1:
                    raise ValueError('Unknown backup format')
                changes = saved['changes']
                for change in changes:
                    current = dict(db.execute(text('SELECT text,translation,meta FROM content_items WHERE id=:id' + (' FOR UPDATE' if args.apply else '')), {'id':change['id']}).mappings().one())
                    if fingerprint(current) != change['after_sha256']:
                        raise ValueError('A repaired record has changed; rollback refused')
                    if args.apply:
                        db.execute(text('UPDATE content_items SET text=:text,translation=:translation,meta=CAST(:meta AS json) WHERE id=:id'), {**change['before'], 'meta':json.dumps(change['before']['meta']), 'id':change['id']})
                print(json.dumps({'mode':'rollback' if args.apply else 'rollback_preview','rows':len(changes)}))
                return
            translations = json.loads(Path(args.translations).read_text())
            trans = {t['verse_key']:t for t in translations['translations']}
            arabic = {v['verse_key']:v['text_uthmani'] for v in json.loads(Path(args.arabic).read_text())['verses']}
            rows = db.execute(text("""SELECT i.id,i.title,i.text,i.translation,i.arabic_text,i.meta
                FROM content_items i JOIN content_sources s ON s.id=i.source_id
                WHERE i.item_type='quran' AND i.org_id IS NULL AND s.org_id IS NULL
                AND s.source_type='quran_foundation' ORDER BY i.id""" + (' FOR UPDATE OF i' if args.apply else ''))).mappings().all()
            changes=[]; unchanged=0; notes=0
            for raw in rows:
                row=dict(raw); key=(row['meta'] or {}).get('verse_key')
                if key not in trans or key not in arabic:
                    raise ValueError('Provider evidence is missing a library verse')
                updated=verified_translation_repair(row, trans[key], arabic[key], translations['meta'])
                before={k:row[k] for k in ('text','translation','meta')}
                if updated==before:
                    unchanged+=1;continue
                notes += len(updated['meta']['quran_translation']['footnotes'])
                changes.append({'id':row['id'],'verse_key':key,'before':before,'after':updated,'after_sha256':fingerprint(updated)})
            if args.apply:
                if not args.backup: raise ValueError('--apply requires a new --backup path')
                # Create and fsync the rollback evidence before any UPDATE.
                fd=os.open(args.backup, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
                with os.fdopen(fd,'w') as f:
                    json.dump({'version':1,'changes':changes},f,ensure_ascii=False);f.flush();os.fsync(f.fileno())
                for change in changes:
                    db.execute(text('UPDATE content_items SET text=:text,translation=:translation,meta=CAST(:meta AS json) WHERE id=:id'), {**change['after'],'meta':json.dumps(change['after']['meta']), 'id':change['id']})
            print(json.dumps({'mode':'applied' if args.apply else 'preview','changed':len(changes),'unchanged':unchanged,'provider_note_markers':notes}))
    finally:
        engine.dispose()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--translations');parser.add_argument('--arabic')
    parser.add_argument('--backup');parser.add_argument('--apply',action='store_true');parser.add_argument('--rollback')
    args=parser.parse_args()
    if not args.rollback and not (args.translations and args.arabic):parser.error('Provide both evidence files or --rollback')
    try:run(args)
    except Exception as error:
        # Database exception strings may include connection credentials or data.
        print('Repair failed; transaction rolled back. Error type: '+type(error).__name__,file=sys.stderr)
        raise SystemExit(1)

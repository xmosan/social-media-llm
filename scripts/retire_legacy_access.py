"""Preview, then retire legacy sign-ins without deleting accounts or creator work.

Operator-only maintenance, never app startup. Take and verify a fresh durable
backup first. Supply the exact reviewed user IDs when applying. The audit contains
only access/scheduling state (no credentials or content) for deliberate rollback;
do not automatically restore flags after an account is invited back.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.creator_access import legacy_access_plan, retire_legacy_access


def preserved_data(connection):
    exclusions = {
        'users': ['is_active', 'is_superadmin', 'session_version', 'updated_at'],
        'orgs': ['tester_revoked_at'], 'api_keys': ['revoked_at'],
        'posts': ['status', 'scheduled_time', 'updated_at'],
        'topic_automations': ['enabled', 'updated_at'],
        'org_members': [], 'ig_accounts': [], 'content_items': [], 'media_assets': [],
        'tester_invitations': [],
    }
    result = {}
    for table, excluded in exclusions.items():
        expression = 'to_jsonb(t)' + ''.join(" - '" + name + "'" for name in excluded)
        query = f"SELECT count(*) count, md5(coalesce(string_agg(({expression})::text, chr(10) ORDER BY id),'')) digest FROM {table} t"
        result[table] = dict(connection.execute(text(query)).mappings().one())
    return result


def access_state(connection):
    columns = {'users':'id,is_active,is_superadmin,session_version,updated_at',
        'orgs':'id,tester_revoked_at', 'api_keys':'id,org_id,revoked_at',
        'topic_automations':'id,org_id,enabled', 'posts':'id,org_id,status,scheduled_time'}
    return {table:[dict(r) for r in connection.execute(text(f'SELECT {fields} FROM {table} ORDER BY id')).mappings()]
            for table, fields in columns.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', required=True)
    parser.add_argument('--owner-email', required=True)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--expected-users', type=int, nargs='+')
    parser.add_argument('--audit', type=Path)
    args = parser.parse_args()
    if args.apply and (not args.expected_users or not args.audit):
        parser.error('Applying requires exact --expected-users and a new private --audit file')
    values = dotenv_values(args.env_file)
    url = make_url(values['DATABASE_URL'])
    if url.get_backend_name() not in {'postgres','postgresql'}:
        parser.error('PostgreSQL required')
    engine = create_engine(url.set(drivername='postgresql+psycopg'), hide_parameters=True,
        connect_args={'connect_timeout':10,'options':'-c statement_timeout=30000 -c lock_timeout=5000'})
    try:
        with Session(engine) as db:
            if not args.apply:
                db.execute(text('SET TRANSACTION READ ONLY'))
                print(json.dumps(legacy_access_plan(db,args.owner_email)))
                return
            # Freeze relevant access state while capturing and applying the plan.
            db.execute(text('LOCK TABLE users, orgs, org_members, api_keys, posts, topic_automations, tester_invitations IN SHARE ROW EXCLUSIVE MODE'))
            before = preserved_data(db.connection())
            state = access_state(db.connection())
            plan = legacy_access_plan(db,args.owner_email)
            if plan['user_ids'] != sorted(set(args.expected_users)):
                raise RuntimeError('Preview no longer matches')
            audit = {'phase':'prepared','recorded_at':datetime.now(timezone.utc).isoformat(),
                     'plan':plan,'before_access':state,'preserved_before':before}
            with os.fdopen(os.open(args.audit,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w') as f:
                json.dump(audit,f,default=str);f.flush();os.fsync(f.fileno())
            retire_legacy_access(db,owner_email=args.owner_email,expected_user_ids=args.expected_users)
            after = preserved_data(db.connection())
            if before != after:
                raise RuntimeError('Unexpected change to preserved creator data')
            audit['after_access'] = access_state(db.connection())
            # Explicitly prove that owner/pilot user rows and protected workspace
            # access state were untouched before committing the transaction.
            before_users={r['id']:r for r in state['users']}
            for row in audit['after_access']['users']:
                if row['id'] not in plan['user_ids'] and row != before_users[row['id']]:
                    raise RuntimeError('Protected user changed')
            before_orgs={r['id']:r for r in state['orgs']}
            for row in audit['after_access']['orgs']:
                if row['id'] in plan['protected_workspace_ids'] and row != before_orgs[row['id']]:
                    raise RuntimeError('Protected workspace changed')
            db.commit()
            audit.update(phase='committed',preserved_after=after)
            args.audit.write_text(json.dumps(audit,default=str))
            print(json.dumps({'committed':True,'disabled_accounts':len(plan['user_ids']),
                'disabled_workspaces':len(plan['workspace_ids']),'preserved_data_verified':True}))
    except Exception as error:
        # Provider errors and SQL parameters can contain credentials/private data.
        print(json.dumps({'completed':False,'error_type':type(error).__name__}))
        raise SystemExit(1)
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()

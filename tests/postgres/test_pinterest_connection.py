"""Real PostgreSQL migration, callback replay and refresh serialization."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock,patch
import threading,unittest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.db import engine
from app.models import Base,Org,User,PinterestConnection as Connection,PinterestConnectionAttempt as Attempt
from app.services import pinterest_connection as service
from app.services.channels.pinterest import PinterestError
from scripts.migrate_pinterest_connections import migrate

class PinterestPostgresChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert engine.url.database=='sabeel_test' and engine.url.query.get('host','').startswith('/tmp/sabeel-pg-test-')
        Base.metadata.create_all(engine)

    def setUp(self):
        with engine.begin() as c:c.execute(text('TRUNCATE '+', '.join('"'+t.name+'"' for t in Base.metadata.sorted_tables)+' RESTART IDENTITY CASCADE'))
        with Session(engine) as db:
            db.add(Org(id=1,name='Fixture'));db.flush();db.add(User(id=1,email='fixture@example.test',active_org_id=1));db.commit()
        self.request=SimpleNamespace(session={})

    def test_additive_migration_from_absence_is_repeatable(self):
        with engine.begin() as c:
            c.execute(text('DROP TABLE pinterest_connection_attempts'));c.execute(text('DROP TABLE pinterest_connections'))
            migrate(c);migrate(c)
        with Session(engine) as db:
            service.begin(db,self.request,1,1);self.assertEqual(db.get(Org,1).name,'Fixture')

    def test_concurrent_callback_consumes_one_state(self):
        with Session(engine) as db:state=service.begin(db,self.request,1,1)
        barrier=threading.Barrier(2)
        def claim(_):
            with Session(engine) as db:
                barrier.wait(timeout=10)
                try:service.claim(db,self.request,1,1,state);return 200
                except HTTPException as e:return e.status_code
        with ThreadPoolExecutor(2) as pool:self.assertEqual(sorted(pool.map(claim,range(2))),[200,400])

    def test_concurrent_reads_rotate_refresh_once(self):
        tokens={'access_token':'synthetic','refresh_token':'synthetic-old','expires_in':3600,'scope':'synthetic'}
        with Session(engine) as db:
            state=service.begin(db,self.request,1,1);attempt=service.claim(db,self.request,1,1,state)
            row=service.store(db,attempt,tokens,{'username':'fixture'},True)
            row.expires_at=service.utcnow()-timedelta(seconds=1);db.commit()
        api=Mock(sandbox=True);api.refresh.return_value={**tokens,'access_token':'new-access','refresh_token':'rotated-refresh'}
        barrier=threading.Barrier(2)
        def read(_):
            with Session(engine) as db:
                barrier.wait(timeout=10)
                try:return service.token(db,1,api)
                except PinterestError:return 'pending'
        with ThreadPoolExecutor(2) as pool:
            results=list(pool.map(read,range(2)));self.assertIn('new-access',results)
            self.assertTrue(set(results)<={'new-access','pending'})
        api.refresh.assert_called_once_with('synthetic-old')
        with Session(engine) as db:
            self.assertEqual(service.token(db,1,api),'new-access')
            self.assertEqual(service.decrypt(db.query(Connection).one())['refresh_token'],'rotated-refresh')

    def test_concurrent_sandbox_setup_creates_one_board(self):
        with Session(engine) as db:
            state=service.begin(db,self.request,1,1);attempt=service.claim(db,self.request,1,1,state)
            service.store(db,attempt,{'access_token':'synthetic','expires_in':3600},{'username':'fixture'},True)
        api=Mock(sandbox=True)
        api.create_test_board.return_value={'id':'123','name':'Test','privacy':'PUBLIC','owner':{'username':'fixture'}}
        barrier=threading.Barrier(2)
        def setup(_):
            with Session(engine) as db:
                barrier.wait(timeout=10)
                return service.setup_test_board(db,1,api)
        with patch.object(service.settings,'pinterest_sandbox',True),ThreadPoolExecutor(2) as pool:
            results=list(pool.map(setup,range(2)))
        self.assertEqual(sorted(r['reused'] for r in results),[False,True])
        self.assertEqual({r['id'] for r in results},{'123'})
        api.create_test_board.assert_called_once_with('synthetic')

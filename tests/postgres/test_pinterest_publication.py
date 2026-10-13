"""Two real PostgreSQL sessions must not send the same Pin twice."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import threading, unittest
from unittest.mock import Mock, patch
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.db import engine
from app.config import settings
from app.models import Base, Org, User, Post, PinterestConnection
from app.services import pinterest_connection as connection, pinterest_publishing as service, post_service
from app.services.media_sequence import card_digest, seal_manifest


class PinterestPublicationPostgresChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert engine.url.database=='sabeel_test' and engine.url.query.get('host','').startswith('/tmp/sabeel-pg-test-')
        Base.metadata.create_all(engine)

    def setUp(self):
        with engine.begin() as c:c.execute(text('TRUNCATE '+', '.join('"'+t.name+'"' for t in Base.metadata.sorted_tables)+' RESTART IDENTITY CASCADE'))
        self.copy={'title':'Fixture 1','description':'Fixture 1','alt_text':'Synthetic card','ai_modified':False,'link':None}
        self.api=Mock(sandbox=True);self.api.account.return_value={'username':'fixture'}
        self.api.board.return_value={'id':'123','privacy':'PUBLIC','owner':{'username':'fixture'}}
        self.api.create_pin.return_value={'id':'456','sandbox':True}
        for patcher in (patch.object(settings,'pinterest_sandbox',True),patch.object(service,'image_digest',return_value='synthetic')):
            patcher.start();self.addCleanup(patcher.stop)
        with Session(engine) as db:
            db.add(Org(id=1,name='Fixture'));db.flush();db.add(User(id=1,email='fixture@example.test',active_org_id=1));db.flush()
            db.add(PinterestConnection(org_id=1,user_id=1,username='fixture',active=True,sandbox=True,
                encrypted_tokens=connection.encrypt({'access_token':'synthetic','refresh_token':'synthetic'},1),
                expires_at=connection.utcnow()+timedelta(hours=1),board_id='123',board_name='Fixture'))
            card={'eyebrow':'Fixture 1','headline':'Synthetic source','arabic_text':'نص تجريبي','supporting_text':''}
            manifest=seal_manifest({'version':1,'format':'feed_4_5','card_digest':card_digest(card),'pages':[
                {'index':0,'url':'https://res.cloudinary.com/fixture/image/upload/card.jpg','width':1080,'height':1350,'quality':{'status':'passed'}}]},1)
            db.add(Post(id=1,org_id=1,status='drafted',source_type='quran',source_reference='Fixture 1',source_text=card['headline'],
                source_metadata={'reference':'Fixture 1','translation_text':card['headline'],'arabic_text':card['arabic_text']},
                card_message=card,caption='Preserved caption',post_format='feed_4_5',media_url=manifest['pages'][0]['url'],
                flags={'media_manifest':manifest,'reviewed_manifest':card_digest(manifest)}));db.commit()
            self.receipt=service.review(db,1,1,1,self.copy)['receipt']

    def send(self):
        with Session(engine) as db:
            try:return service.publish(db,1,1,1,self.copy,self.receipt,self.api)['status']
            except HTTPException as error:return error.status_code

    def test_concurrent_publish_sends_exactly_once(self):
        barrier=threading.Barrier(2)
        def send(_):barrier.wait(timeout=10);return self.send()
        with ThreadPoolExecutor(2) as pool:
            outcomes=list(pool.map(send,range(2)))
        self.assertIn('published',outcomes);self.assertTrue(set(outcomes)<={'published',409})
        self.api.create_pin.assert_called_once()
        with Session(engine) as db:
            post=db.get(Post,1);self.assertEqual(post.caption,'Preserved caption');self.assertEqual(post.status,'drafted')
            self.assertEqual(post.flags[service.KEY]['pin_id'],'456')

    def test_committed_pending_claim_blocks_other_worker_and_edits(self):
        entered=threading.Event();release=threading.Event()
        def create(*args):
            entered.set();release.wait(timeout=10);return {'id':'456','sandbox':True}
        self.api.create_pin.side_effect=create
        with ThreadPoolExecutor(1) as pool:
            task=pool.submit(self.send)
            try:
                self.assertTrue(entered.wait(timeout=10));self.assertEqual(self.send(),409)
                with Session(engine) as db:
                    with self.assertRaises(HTTPException):post_service.get_mutable_post(db,1,1)
            finally:release.set()
            self.assertEqual(task.result(timeout=10),'published')
        self.api.create_pin.assert_called_once()

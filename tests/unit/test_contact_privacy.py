from app.config import settings
from unittest.mock import patch
"""An anonymous contact route must not reveal the private support inbox."""
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.db import get_db
from app.models import User, Org, InboundMessage
from app.api.routes import contact
from app.security.auth import create_access_token
from test_security import DatabaseCase


class ContactPrivacyChecks(DatabaseCase):
    def setUp(self):
        owner = patch.object(settings, "platform_owner_email", "admin@fixture.test")
        owner.start(); self.addCleanup(owner.stop)
        super().setUp()
        InboundMessage.__table__.create(self.engine)
        self.db.add(Org(id=1,name='Synthetic')); self.db.flush()
        self.db.add_all([User(id=1,email='admin@fixture.test',is_superadmin=True), User(id=2,email='creator@fixture.test')])
        self.db.add(InboundMessage(email='private@fixture.test',message='Private fixture body')); self.db.commit()
        app=FastAPI(); app.include_router(contact.router); app.dependency_overrides[get_db]=lambda:self.db
        self.client=TestClient(app); self.addCleanup(self.client.close)

    def test_anonymous_and_creator_cannot_read_support_inbox(self):
        for headers, expected in (({},401),({'Authorization':'Bearer '+create_access_token({'sub':'2'})},403)):
            response=self.client.get('/api/contact/all',headers=headers)
            self.assertEqual(response.status_code,expected)
            self.assertNotIn('private@fixture.test',response.text)
            self.assertNotIn('Private fixture body',response.text)

    def test_admin_retains_access_to_support_inbox(self):
        response=self.client.get('/api/contact/all',headers={'Authorization':'Bearer '+create_access_token({'sub':'1'})})
        self.assertEqual(response.status_code,200); self.assertEqual(len(response.json()),1)

    def test_public_contact_cannot_impersonate_authenticated_pilot_feedback(self):
        response=self.client.post('/api/contact/',json={'email':'outsider@example.com','message':'Synthetic','source':'creator_pilot'})
        self.assertEqual(response.status_code,422); self.assertEqual(self.db.query(InboundMessage).count(),1)

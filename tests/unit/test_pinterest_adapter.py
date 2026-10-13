"""Offline provider contracts only; these do not certify Pinterest app approval."""
from dataclasses import replace
import unittest
from urllib.parse import parse_qs, urlsplit
import httpx
from app.services.channels.pinterest import (
    API, SANDBOX, SCOPES, PinDraft, PinterestClient, PinterestCredentials,
    PinterestError, PinterestOutcomeUnknown,
)

CREDS= PinterestCredentials('test-app', 'synthetic-client-secret', 'https://app.example.test/auth/pinterest/callback')
DRAFT=PinDraft('123', 'https://res.cloudinary.com/fixture/image/upload/one.jpg', 'A reminder',
               'Separately reviewed social copy.', 'Arabic and English reminder on cream paper.', True)


class PinterestAdapterTests(unittest.TestCase):
    def client(self, response=None, *, handler=None, sandbox=True):
        self.requests=[]
        def transport(request):
            self.requests.append(request)
            return handler(request) if handler else response
        client= PinterestClient(CREDS, sandbox=sandbox, transport=httpx.MockTransport(transport))
        self.addCleanup(client.close)
        return client

    def test_oauth_has_exact_callback_state_and_only_required_scopes(self):
        c=self.client(); url=c.authorization_url('a'*43); query=parse_qs(urlsplit(url).query)
        self.assertEqual(urlsplit(url).netloc,'www.pinterest.com')
        self.assertEqual(query['redirect_uri'],[CREDS.redirect_uri])
        self.assertEqual(query['scope'],[','.join(SCOPES)])
        self.assertNotIn(CREDS.client_secret,url)
        self.assertNotIn(CREDS.client_secret,repr(CREDS))
        with self.assertRaises(PinterestError):c.authorization_url('')
        with self.assertRaises(PinterestError):PinterestClient(replace(CREDS,redirect_uri='https://user:secret@site.test/callback'))

    def test_exchange_and_refresh_preserve_rotated_secrets_and_do_not_log_them(self):
        token={'access_token':'synthetic-access','refresh_token':'synthetic-new-refresh','token_type':'bearer',
               'expires_in':3600,'scope':' '.join(SCOPES),'refresh_token_expires_at':9999999999}
        c=self.client(httpx.Response(200,json=token))
        self.assertEqual(c.exchange_code('synthetic-code')['refresh_token'],'synthetic-new-refresh')
        self.assertEqual(str(self.requests[0].url),API+'/oauth/token')
        self.assertTrue(self.requests[0].headers['Authorization'].startswith('Basic '))
        self.assertEqual(parse_qs(self.requests[0].content.decode())['redirect_uri'],[CREDS.redirect_uri])
        self.assertEqual(c.refresh('synthetic-old')['refresh_token'],'synthetic-new-refresh')
        self.assertEqual(parse_qs(self.requests[1].content.decode())['grant_type'],['refresh_token'])

    def test_incomplete_token_never_becomes_a_connection(self):
        c=self.client(httpx.Response(200,json={'access_token':'synthetic-access','scope':'boards:read'}))
        with self.assertRaises(PinterestError):c.exchange_code('code')
        self.assertEqual(len(self.requests),1)

    def test_missing_token_and_ambiguous_environment_fail_before_network(self):
        c=self.client(httpx.Response(200,json={'username':'fixture'}))
        for token in (None, '', ' ', 'synthetic\r\ninvalid', 123):
            with self.subTest(token=repr(token)), self.assertRaises(PinterestError):
                c.account(token)
        self.assertEqual(self.requests,[])
        for sandbox in ('false', 0, None):
            with self.assertRaises(PinterestError):
                PinterestClient(CREDS,sandbox=sandbox)

    def test_pin_payload_preserves_copy_unicode_and_ai_disclosure_exactly(self):
        draft=replace(DRAFT,description='Separate caption\nنص تجريبي ﷺ')
        c=self.client(httpx.Response(201,json={'id':'456'}))
        result=c.create_pin('synthetic-token',draft)
        self.assertEqual(result,{'id':'456','sandbox':True})
        self.assertEqual(str(self.requests[0].url),SANDBOX+'/pins')
        import json
        payload=json.loads(self.requests[0].content)
        self.assertEqual(payload['description'],draft.description)
        self.assertEqual(payload['ai_disclosures'],{'values':['AI_MODIFIED']})
        self.assertNotIn('ai_disclosures',replace(draft,ai_modified=False).payload())
        self.assertEqual(draft.image_url,DRAFT.image_url)

    def test_oversized_copy_and_unstable_media_fail_before_a_request(self):
        c=self.client(httpx.Response(200,json={'id':'1'}))
        changes=[{'title':'x'*101},{'description':'x'*801},{'alt_text':'x'*501},
                 {'description':''},{'board_id':'123/../../oauth/token'},
                 {'image_url':'https://unknown.example/test.jpg'},
                 {'link':'https://name:password@example.test'},{'ai_modified':None}]
        for change in changes:
            with self.subTest(change=list(change)), self.assertRaises(PinterestError):
                c.create_pin('synthetic',replace(DRAFT,**change))
        self.assertEqual(self.requests,[])

    def test_timeouts_server_errors_and_missing_ids_are_never_retried(self):
        for response in (httpx.Response(503,json={'message':'synthetic-token'}),
                         httpx.Response(408),httpx.Response(200,json={}),
                         httpx.Response(201,content=b'not-json')):
            with self.subTest(status=response.status_code):
                c=self.client(response)
                with self.assertRaises(PinterestOutcomeUnknown) as error:c.create_pin('synthetic-token',DRAFT)
                self.assertNotIn('synthetic-token',str(error.exception));self.assertEqual(len(self.requests),1)
        def fail(request):raise httpx.ReadTimeout('synthetic-token',request=request)
        c=self.client(handler=fail)
        with self.assertRaises(PinterestOutcomeUnknown):c.create_pin('synthetic-token',DRAFT)
        self.assertEqual(len(self.requests),1)

    def test_rejections_do_not_leak_credentials_or_retry(self):
        for status in (400,401,403,429):
            c=self.client(httpx.Response(status,json={'message':'synthetic-token'}))
            with self.assertRaises(PinterestError) as error:c.create_pin('synthetic-token',DRAFT)
            self.assertNotIsInstance(error.exception,PinterestOutcomeUnknown)
            self.assertNotIn('synthetic-token',str(error.exception));self.assertEqual(len(self.requests),1)

    def test_redirect_does_not_forward_token_or_duplicate_write(self):
        c=self.client(httpx.Response(302,headers={'location':'https://other.test'}))
        with self.assertRaises(PinterestOutcomeUnknown):c.create_pin('synthetic',DRAFT)
        self.assertEqual(len(self.requests),1)

    def test_empty_board_page_preserves_bookmark_and_queries_only_public_boards(self):
        c=self.client(httpx.Response(200,json={'items':[],'bookmark':'next page'}))
        self.assertEqual(c.boards('synthetic')['bookmark'],'next page')
        c.boards('synthetic','next page')
        query=parse_qs(urlsplit(str(self.requests[-1].url)).query)
        self.assertEqual(query,{'page_size':['100'],'privacy':['PUBLIC'],'bookmark':['next page']})

    def test_identity_missing_and_invalid_ids_fail_clearly(self):
        c=self.client(httpx.Response(200,json={}))
        with self.assertRaises(PinterestError):c.account('synthetic')
        for identifier in ('../oauth/token',123,'',None):
            with self.assertRaises(PinterestError):c.board('synthetic',identifier)
        self.assertEqual(len(self.requests),1)

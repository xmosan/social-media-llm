"""Owner-pilot connection lifecycle; no scheduler or public Pin writes."""
import base64
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import secrets

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException
from sqlalchemy import delete, or_, update
from app.config import settings
from app.models import PinterestConnection as Connection, PinterestConnectionAttempt as Attempt, Org
from app.services.channels.pinterest import PinterestClient, PinterestCredentials, PinterestError, _identifier
from app.services.instagram_connection import digest, utcnow


def client():
    return PinterestClient(PinterestCredentials(settings.pinterest_client_id or '',
        settings.pinterest_client_secret or '', settings.public_base_url.rstrip('/') + '/auth/pinterest/callback'),
        sandbox=settings.pinterest_sandbox)


def cipher():
    key = hmac.new(settings.secret_key.encode(), b'sabeel-pinterest-connection-v1', hashlib.sha256).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt(tokens, org_id):
    return cipher().encrypt(json.dumps({'org_id':org_id,'tokens':tokens}).encode()).decode()


def decrypt(row):
    try:
        data = json.loads(cipher().decrypt(row.encrypted_tokens.encode()))
        if data['org_id'] != row.org_id:
            raise ValueError()
        return data['tokens']
    except (InvalidToken, ValueError, TypeError, AttributeError, KeyError):
        raise PinterestError('Reconnect Pinterest to restore secure access.') from None


def begin(db, request, user_id, org_id):
    state, handle = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    db.execute(delete(Attempt).where(or_(Attempt.expires_at <= utcnow(), Attempt.user_id == user_id)))
    db.add(Attempt(id=digest(handle),user_id=user_id,org_id=org_id,state_hash=digest(state),
                   stage='pending',expires_at=utcnow()+timedelta(minutes=15)))
    db.commit()
    request.session['pinterest_connection'] = handle
    return state


def claim(db, request, user_id, org_id, state):
    handle=request.session.get('pinterest_connection')
    if not isinstance(handle,str) or not 20 <= len(handle) <= 128:
        raise HTTPException(401,'Start a new Pinterest connection from Sabeel.')
    if not isinstance(state,str) or not 20 <= len(state) <= 128:
        raise HTTPException(400,'Pinterest connection could not be verified.')
    row_id=db.execute(update(Attempt).where(Attempt.id==digest(handle),Attempt.user_id==user_id,
        Attempt.org_id==org_id,Attempt.state_hash==digest(state),Attempt.stage=='pending',
        Attempt.expires_at>utcnow()).values(stage='exchanging').returning(Attempt.id)).scalar_one_or_none()
    db.commit()
    if not row_id:
        raise HTTPException(400,'Pinterest connection expired or was already used. Start again.')
    return row_id


def abandon(db, request, attempt_id):
    db.execute(delete(Attempt).where(Attempt.id==attempt_id));db.commit()
    request.session.pop('pinterest_connection',None)


def store(db, attempt_id, tokens, identity, sandbox):
    """Consume the callback and store credentials in one atomic transaction."""
    attempt=db.query(Attempt).filter(Attempt.id==attempt_id,Attempt.stage=='exchanging',
        Attempt.expires_at>utcnow()).with_for_update().first()
    if not attempt:
        raise PinterestError('This connection expired. Connect Pinterest again.')
    username=identity.get('username')
    if not isinstance(username,str) or not 1 <= len(username) <= 150:
        raise PinterestError('Pinterest account identity could not be verified.')
    db.query(Org).filter(Org.id==attempt.org_id).with_for_update().one()
    row=db.query(Connection).filter_by(org_id=attempt.org_id).with_for_update().first()
    if row is None:
        row=Connection(org_id=attempt.org_id,user_id=attempt.user_id);db.add(row)
    # Reconnection never silently retains a board belonging to another identity.
    row.board_id=row.board_name=None
    row.username=username;row.user_id=attempt.user_id;row.sandbox=sandbox
    row.encrypted_tokens=encrypt(tokens,row.org_id)
    row.expires_at=utcnow()+timedelta(seconds=tokens['expires_in']);row.active=True;row.refresh_pending=False
    db.delete(attempt);db.commit()
    return row


def connection(db, org_id):
    return db.query(Connection).filter_by(org_id=org_id).first()


def token(db, org_id, api):
    # Persist a refresh claim before network I/O. A process crash or failed DB
    # commit after provider rotation must not replay a consumed refresh token.
    row=db.query(Connection).filter_by(org_id=org_id).populate_existing().with_for_update().first()
    if not row or not row.active or row.sandbox != api.sandbox:
        db.rollback();raise PinterestError('Connect Pinterest in the current test environment first.')
    if row.refresh_pending:
        db.rollback();raise PinterestError('Pinterest renewal is in progress or was interrupted. Reload shortly; reconnect if it persists.')
    try:
        tokens=decrypt(row)
        expiry=row.expires_at
        if expiry is None:
            raise PinterestError('Reconnect Pinterest to renew access.')
        if expiry.tzinfo is None:expiry=expiry.replace(tzinfo=timezone.utc)
        if expiry > utcnow()+timedelta(minutes=5):
            access=tokens['access_token'];db.commit();return access
    except (PinterestError,KeyError,ValueError):
        row.active=False;row.encrypted_tokens=None;row.expires_at=None
        db.commit()
        raise PinterestError('Pinterest access needs to be renewed. Reconnect the account; your saved drafts are retained.') from None
    original=row.encrypted_tokens;row.refresh_pending=True;db.commit()
    try:
        refreshed=api.refresh(tokens['refresh_token'])
    except PinterestError:
        row=db.query(Connection).filter_by(org_id=org_id).populate_existing().with_for_update().one()
        if row.refresh_pending and row.encrypted_tokens==original:
            row.active=False;row.encrypted_tokens=None;row.expires_at=None;row.refresh_pending=False
        db.commit()
        raise PinterestError('Pinterest renewal could not be confirmed. Reconnect the account; your saved drafts are retained.') from None
    row=db.query(Connection).filter_by(org_id=org_id).populate_existing().with_for_update().one()
    if not row.active or not row.refresh_pending or row.encrypted_tokens!=original or row.sandbox!=api.sandbox:
        db.rollback();raise PinterestError('The connection changed during renewal. Reload the connection page.')
    row.encrypted_tokens=encrypt(refreshed,org_id)
    row.expires_at=utcnow()+timedelta(seconds=refreshed['expires_in']);row.refresh_pending=False
    db.commit();return refreshed['access_token']


def boards(db, org_id, api, bookmark=None):
    access=token(db,org_id,api)
    page=api.boards(access,bookmark)
    row=connection(db,org_id)
    items=[]
    for item in page['items']:
        if not isinstance(item,dict):continue
        owner=(item.get('owner') or {}).get('username')
        if owner != row.username or item.get('privacy') != 'PUBLIC':continue
        try:board_id=_identifier(item.get('id'))
        except PinterestError:continue
        items.append({'id':board_id,'name':str(item.get('name') or 'Untitled board')[:255]})
    cursor=page.get('bookmark')
    if cursor is not None and (not isinstance(cursor,str) or len(cursor)>4096):
        raise PinterestError('Pinterest returned invalid pagination. Reload the boards.')
    return {'items':items,'bookmark':cursor}


def choose_board(db, org_id, api, board_id):
    access=token(db,org_id,api)
    board=api.board(access,board_id)
    row=db.query(Connection).filter_by(org_id=org_id).populate_existing().with_for_update().one()
    if (not row.active or row.sandbox!=api.sandbox or decrypt(row).get('access_token')!=access
            or board.get('id')!=board_id or board.get('privacy')!='PUBLIC'
            or (board.get('owner') or {}).get('username')!=row.username):
        db.rollback();raise PinterestError('Choose a public board owned by the connected account.')
    row.board_id=board_id;row.board_name=str(board.get('name') or 'Untitled board')[:255]
    db.commit()


def disconnect(db, request, user_id, org_id):
    row=db.query(Connection).filter_by(org_id=org_id).with_for_update().first()
    if row:
        row.active=False;row.encrypted_tokens=None;row.expires_at=None;row.board_id=row.board_name=None;row.refresh_pending=False
    # Revoke outstanding local handoffs so an in-flight callback cannot reconnect.
    db.execute(delete(Attempt).where(Attempt.user_id==user_id,Attempt.org_id==org_id))
    db.commit();request.session.pop('pinterest_connection',None)


def setup_test_board(db, org_id, api):
    """Explicit owner setup; never create a production board or retry a write."""
    if not settings.pinterest_sandbox or not api.sandbox:
        raise PinterestError('Test board setup is available only in Sandbox.')
    access=token(db,org_id,api)
    row=db.query(Connection).filter_by(org_id=org_id).populate_existing().with_for_update().one()
    if not row.active or not row.sandbox or decrypt(row).get('access_token')!=access:
        raise PinterestError('The connection changed. Reload the Sandbox connection first.')
    # Serializes simultaneous setup clicks; a selected board is reused.
    if row.board_id:
        return {'id':row.board_id,'name':row.board_name,'reused':True}
    board=api.create_test_board(access)
    if (board.get('privacy')!='PUBLIC' or (board.get('owner') or {}).get('username')!=row.username):
        raise PinterestError('The returned test board could not be verified. Load your boards; do not create another automatically.')
    row.board_id=_identifier(board.get('id'));row.board_name=str(board.get('name') or 'Sandbox test')[:255]
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise PinterestError('The board result could not be saved. Load your boards and select the existing test board; do not create another.') from None
    return {'id':row.board_id,'name':row.board_name,'reused':False}

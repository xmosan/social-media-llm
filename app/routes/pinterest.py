"""Owner-only Pinterest trial: connection, board selection and reviewed test Pins."""
from contextlib import contextmanager
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from pydantic import BaseModel, Field, StrictBool
from sqlalchemy.orm import Session
from app.config import settings
from app.db import get_db
from app.models import User, Post
from app.security.rbac import require_superadmin, get_current_org_id, OWNER_HEADERS
from app.services import pinterest_connection as connection
from app.services.instagram_connection import require_same_origin
from app.services.usage_limits import check_auth_attempt
from app.logging_setup import log_event
from app.services import pinterest_publishing as publishing

router=APIRouter(tags=['owner-pinterest-pilot'])
templates=Jinja2Templates(directory=str(Path(__file__).resolve().parents[1]/'templates'))
HOME='/admin/connections/pinterest'
# Native POST forms need a non-null Origin for the owner/CSRF checks. Keep
# referrers inside Sabeel; OAuth redirects and callbacks still use no-referrer.
PAGE_HEADERS={**OWNER_HEADERS,'Referrer-Policy':'same-origin'}


@contextmanager
def api_client():
    api=None
    try:
        api=connection.client();yield api
    except ValueError as error:
        raise HTTPException(422,str(error),headers=OWNER_HEADERS) from None
    finally:
        if api:api.close()


def redirect(result):
    return RedirectResponse(HOME+'?result='+result,status_code=303,headers=OWNER_HEADERS)


@router.get(HOME)
def page(request:Request,db:Session=Depends(get_db),user:User=Depends(require_superadmin),
         org_id:int=Depends(get_current_org_id)):
    row=connection.connection(db,org_id)
    messages={'connected':'Pinterest connected. Load your public boards below.',
              'cancelled':'Connection cancelled. Your previous connection was kept.',
              'unavailable':'Pinterest could not complete the connection. Try again; existing drafts are retained.',
              'disconnected':'Pinterest disconnected from Sabeel. You can also remove Sabeel in Pinterest settings.'}
    return templates.TemplateResponse(request=request,name='pinterest-pilot.html',context={
        'configured':bool(settings.pinterest_client_id and settings.pinterest_client_secret),
        'connected':bool(row and row.active and row.sandbox==settings.pinterest_sandbox),
        'username':row.username if row else '', 'board_name':row.board_name if row else '',
        'sandbox':settings.pinterest_sandbox,'message':messages.get(request.query_params.get('result'),''),
        'callback':settings.public_base_url.rstrip('/')+'/auth/pinterest/callback'},headers=PAGE_HEADERS)


@router.post('/auth/pinterest/login')
def login(request:Request,db:Session=Depends(get_db),user:User=Depends(require_superadmin),
          org_id:int=Depends(get_current_org_id)):
    require_same_origin(request);check_auth_attempt(str(user.id))
    with api_client() as api:
        state=connection.begin(db,request,user.id,org_id)
        return RedirectResponse(api.authorization_url(state),status_code=303,headers=OWNER_HEADERS)


@router.get('/auth/pinterest/callback')
def callback(request:Request,code:str|None=None,state:str|None=None,db:Session=Depends(get_db),
             user:User=Depends(require_superadmin),org_id:int=Depends(get_current_org_id)):
    attempt=connection.claim(db,request,user.id,org_id,state)
    if request.query_params.get('error') or not code:
        connection.abandon(db,request,attempt);return redirect('cancelled')
    try:
        with api_client() as api:
            tokens=api.exchange_code(code);identity=api.account(tokens['access_token'])
            connection.store(db,attempt,tokens,identity,api.sandbox)
        request.session.pop('pinterest_connection',None)
    except Exception:
        db.rollback();connection.abandon(db,request,attempt)
        log_event('pinterest_connection_failed',level='warning')
        return redirect('unavailable')
    return redirect('connected')


@router.get('/api/pinterest/boards')
def boards(bookmark:str|None=None,db:Session=Depends(get_db),user:User=Depends(require_superadmin),
           org_id:int=Depends(get_current_org_id)):
    with api_client() as api:return connection.boards(db,org_id,api,bookmark)


class BoardChoice(BaseModel):
    board_id:str=Field(min_length=1,max_length=64,pattern=r'^[0-9]+$')


@router.post('/api/pinterest/board')
def choose(payload:BoardChoice,request:Request,db:Session=Depends(get_db),user:User=Depends(require_superadmin),
           org_id:int=Depends(get_current_org_id)):
    require_same_origin(request)
    with api_client() as api:connection.choose_board(db,org_id,api,payload.board_id)
    return {'ok':True}


@router.post('/auth/pinterest/disconnect')
def disconnect(request:Request,db:Session=Depends(get_db),user:User=Depends(require_superadmin),
               org_id:int=Depends(get_current_org_id)):
    require_same_origin(request);connection.disconnect(db,request,user.id,org_id)
    return redirect('disconnected')


class PinCopy(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=800)
    alt_text: str = Field(min_length=1, max_length=500)
    ai_modified: StrictBool
    link: str | None = Field(default=None, max_length=2048)


class ReviewedPin(PinCopy):
    receipt: str = Field(min_length=1, max_length=2048)
    reviewed: StrictBool


@router.get('/api/pinterest/posts')
def available_posts(db:Session=Depends(get_db),user:User=Depends(require_superadmin),
                    org_id:int=Depends(get_current_org_id)):
    rows=db.query(Post).filter(Post.org_id==org_id,Post.post_format=='feed_4_5').order_by(Post.id.desc()).limit(50).all()
    return {'items':[{'id':p.id,'reference':p.source_reference or 'Saved card',
                       'publication':publishing.state(p)} for p in rows]}


@router.get('/api/pinterest/posts/{post_id}')
def post_status(post_id:int,db:Session=Depends(get_db),user:User=Depends(require_superadmin),
                org_id:int=Depends(get_current_org_id)):
    return publishing.state(publishing.get_post(db,post_id,org_id))


@router.post('/api/pinterest/posts/{post_id}/review')
def review_pin(post_id:int,payload:PinCopy,request:Request,db:Session=Depends(get_db),
               user:User=Depends(require_superadmin),org_id:int=Depends(get_current_org_id)):
    require_same_origin(request)
    with api_client():
        return publishing.review(db,post_id,org_id,user.id,payload.model_dump())


@router.post('/api/pinterest/posts/{post_id}/publish')
def publish_pin(post_id:int,payload:ReviewedPin,request:Request,db:Session=Depends(get_db),
                 user:User=Depends(require_superadmin),org_id:int=Depends(get_current_org_id)):
    require_same_origin(request)
    if payload.reviewed is not True:
        raise HTTPException(422,'Review the complete card, source, Pin copy and destination first.')
    with api_client() as api:
        return publishing.publish(db,post_id,org_id,user.id,
            payload.model_dump(exclude={'receipt','reviewed'}),payload.receipt,api)


@router.get('/api/pinterest/posts/{post_id}/verify')
def verify_pin(post_id:int,db:Session=Depends(get_db),user:User=Depends(require_superadmin),
                org_id:int=Depends(get_current_org_id)):
    with api_client() as api:return publishing.verify(db,post_id,org_id,api)

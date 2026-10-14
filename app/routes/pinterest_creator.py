"""Workspace-scoped Pin drafts and manually reviewed Standard publishing."""
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import Post, User
from app.security.auth import require_user
from app.security.rbac import get_current_org_id, OWNER_HEADERS
from app.services.instagram_connection import require_same_origin
from app.services import pinterest_drafts as drafts, pinterest_publishing as publishing
from app.services import pinterest_connection as connection
from app.routes.pinterest import api_client, BoardChoice
from app.services.usage_limits import check_auth_attempt


class PrivateRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()
        async def private(request):
            try:
                response = await handler(request)
            except RequestValidationError:
                response = JSONResponse({'detail': 'Check the Pin fields and character limits.'}, status_code=422)
            except HTTPException as error:
                response = JSONResponse({'detail': error.detail}, status_code=error.status_code, headers=error.headers)
            except ValueError as error:
                response = JSONResponse({'detail': str(error)}, status_code=422)
            response.headers.update(OWNER_HEADERS)
            if request.url.path == '/app/pinterest':
                response.headers['Referrer-Policy'] = 'same-origin'
            return response
        return private


router = APIRouter(route_class=PrivateRoute, dependencies=[Depends(require_user), Depends(get_current_org_id)])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / 'templates'))


class DraftCopy(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str = Field(default='', max_length=100)
    description: str = Field(default='', max_length=800)
    alt_text: str = Field(default='', max_length=500)
    ai_modified: StrictBool | None = None
    link: str | None = Field(default=None, max_length=2048)
    revision: int = Field(ge=0, strict=True)
    source_version: str = Field(pattern=r'^[0-9a-f]{64}$')


@router.get('/app/pinterest')
def page(request: Request, post: int | None = Query(default=None, gt=0)):
    messages = {'connected': 'Pinterest connected. Choose your public board below.',
                'cancelled': 'Connection cancelled. Your previous connection and drafts were kept.',
                'unavailable': 'Pinterest could not complete the connection. Try again; your drafts are kept.'}
    return templates.TemplateResponse(request=request, name='pinterest-creator.html', context={
        'post_id': post or '', 'enabled': connection.creator_enabled(),
        'connection_message': messages.get(request.query_params.get('result'), '')})


@router.get('/api/creator/pinterest/posts')
def posts(before: int | None = Query(default=None, gt=0), db: Session = Depends(get_db), org_id: int = Depends(get_current_org_id)):
    query = db.query(Post).filter(Post.org_id == org_id, Post.post_format == 'feed_4_5', Post.card_message.isnot(None))
    if before is not None:
        query = query.filter(Post.id < before)
    rows = query.order_by(Post.id.desc()).limit(31).all()
    return {'items': [{'id': p.id, 'reference': p.source_reference or 'Saved card',
        'has_draft': bool((p.flags or {}).get(drafts.KEY))} for p in rows[:30]],
        'next_before': rows[29].id if len(rows) > 30 else None, 'publishing_enabled': connection.creator_enabled()}


@router.get('/api/creator/pinterest/posts/{post_id}')
def read(post_id: int, db: Session = Depends(get_db), org_id: int = Depends(get_current_org_id)):
    return drafts.read(publishing.get_post(db, post_id, org_id))


@router.put('/api/creator/pinterest/posts/{post_id}')
def save(post_id: int, payload: DraftCopy, request: Request, db: Session = Depends(get_db), org_id: int = Depends(get_current_org_id)):
    require_same_origin(request)
    return drafts.save(db, post_id, org_id, payload.model_dump(exclude={'revision', 'source_version'}),
                       payload.revision, payload.source_version)


@router.get('/api/creator/pinterest/connection')
def status(db: Session = Depends(get_db), org_id: int = Depends(get_current_org_id)):
    row = connection.connection(db, org_id)
    active = bool(row and row.active and not row.refresh_pending and not row.sandbox)
    return {'enabled': connection.creator_enabled(), 'connected': active,
            'username': row.username if active else None,
            'board_id': row.board_id if active else None, 'board_name': row.board_name if active else None}


@router.post('/api/creator/pinterest/connect', dependencies=[Depends(connection.require_creator_enabled)])
def connect(request: Request, studio_post: int | None = Query(default=None, gt=0), db: Session = Depends(get_db), user: User = Depends(require_user),
            org_id: int = Depends(get_current_org_id)):
    require_same_origin(request)
    check_auth_attempt(str(user.id))
    if studio_post is not None:
        publishing.get_post(db, studio_post, org_id)
    with api_client() as api:
        state = connection.begin(db, request, user.id, org_id, creator=True)
        if studio_post is not None:
            request.session['pinterest_studio_post'] = studio_post
        from fastapi.responses import RedirectResponse
        return RedirectResponse(api.authorization_url(state), status_code=303, headers=OWNER_HEADERS)


@router.post('/api/creator/pinterest/disconnect')
def disconnect(request: Request, db: Session = Depends(get_db), user: User = Depends(require_user),
               org_id: int = Depends(get_current_org_id)):
    require_same_origin(request)
    connection.disconnect(db, request, user.id, org_id)
    return {'ok': True}


@router.get('/api/creator/pinterest/boards', dependencies=[Depends(connection.require_creator_enabled)])
def boards(bookmark: str | None = Query(default=None, max_length=4096), db: Session = Depends(get_db),
           org_id: int = Depends(get_current_org_id)):
    with api_client() as api:
        return connection.boards(db, org_id, api, bookmark)


@router.post('/api/creator/pinterest/board', dependencies=[Depends(connection.require_creator_enabled)])
def choose(payload: BoardChoice, request: Request, db: Session = Depends(get_db),
           org_id: int = Depends(get_current_org_id)):
    require_same_origin(request)
    with api_client() as api:
        connection.choose_board(db, org_id, api, payload.board_id)
    return status(db, org_id)


class DraftVersion(BaseModel):
    model_config = ConfigDict(extra='forbid')
    revision: int = Field(ge=1, strict=True)
    source_version: str = Field(pattern=r'^[0-9a-f]{64}$')


class ReviewedDraft(DraftVersion):
    receipt: str = Field(min_length=1, max_length=2048)
    reviewed: StrictBool


@router.post('/api/creator/pinterest/posts/{post_id}/review', dependencies=[Depends(connection.require_creator_enabled)])
def review(post_id: int, payload: DraftVersion, request: Request, db: Session = Depends(get_db),
           user: User = Depends(require_user), org_id: int = Depends(get_current_org_id)):
    require_same_origin(request)
    post = publishing.get_post(db, post_id, org_id)
    copy = drafts.reviewed_copy(post, payload.revision, payload.source_version)
    with api_client():
        return publishing.review(db, post_id, org_id, user.id, copy)


@router.post('/api/creator/pinterest/posts/{post_id}/publish', dependencies=[Depends(connection.require_creator_enabled)])
def publish(post_id: int, payload: ReviewedDraft, request: Request, db: Session = Depends(get_db),
            user: User = Depends(require_user), org_id: int = Depends(get_current_org_id)):
    require_same_origin(request)
    if not payload.reviewed:
        raise HTTPException(422, 'Review the complete image, source, Pin copy and destination first.')
    post = publishing.get_post(db, post_id, org_id)
    if publishing.state(post)['status'] == 'published':
        return {**publishing.state(post), 'already_sent': True}
    copy = drafts.reviewed_copy(post, payload.revision, payload.source_version)
    with api_client() as api:
        return publishing.publish(db, post_id, org_id, user.id, copy, payload.receipt, api,
            draft_version=(payload.revision, payload.source_version))


@router.get('/api/creator/pinterest/posts/{post_id}/status')
def publication_status(post_id: int, db: Session = Depends(get_db), org_id: int = Depends(get_current_org_id)):
    return publishing.state(publishing.get_post(db, post_id, org_id))


@router.get('/api/creator/pinterest/posts/{post_id}/verify', dependencies=[Depends(connection.require_creator_enabled)])
def verify(post_id: int, db: Session = Depends(get_db), org_id: int = Depends(get_current_org_id)):
    with api_client() as api:
        return publishing.verify(db, post_id, org_id, api)


@router.post('/api/creator/pinterest/posts/{post_id}/schedule')
def unavailable(request: Request):
    require_same_origin(request)
    raise HTTPException(403, 'Pinterest scheduling is not available yet. Save a draft and publish it manually when ready.')

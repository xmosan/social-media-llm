"""Private, workspace-scoped Pin drafts. Public Pinterest access is not enabled."""
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
    return templates.TemplateResponse(request=request, name='pinterest-creator.html', context={'post_id': post or ''})


@router.get('/api/creator/pinterest/posts')
def posts(before: int | None = Query(default=None, gt=0), db: Session = Depends(get_db), org_id: int = Depends(get_current_org_id)):
    query = db.query(Post).filter(Post.org_id == org_id, Post.post_format == 'feed_4_5', Post.card_message.isnot(None))
    if before is not None:
        query = query.filter(Post.id < before)
    rows = query.order_by(Post.id.desc()).limit(31).all()
    return {'items': [{'id': p.id, 'reference': p.source_reference or 'Saved card',
        'has_draft': bool((p.flags or {}).get(drafts.KEY))} for p in rows[:30]],
        'next_before': rows[29].id if len(rows) > 30 else None, 'publishing_enabled': False}


@router.get('/api/creator/pinterest/posts/{post_id}')
def read(post_id: int, db: Session = Depends(get_db), org_id: int = Depends(get_current_org_id)):
    return drafts.read(publishing.get_post(db, post_id, org_id))


@router.put('/api/creator/pinterest/posts/{post_id}')
def save(post_id: int, payload: DraftCopy, request: Request, db: Session = Depends(get_db), org_id: int = Depends(get_current_org_id)):
    require_same_origin(request)
    return drafts.save(db, post_id, org_id, payload.model_dump(exclude={'revision', 'source_version'}),
                       payload.revision, payload.source_version)


# Deliberate server-side release boundary. Neither Sandbox settings nor an owner
# session can enable publishing through creator endpoints. Activation requires a
# reviewed release after Standard approval, not a client-side button change.
@router.post('/api/creator/pinterest/connect')
@router.post('/api/creator/pinterest/posts/{post_id}/publish')
@router.post('/api/creator/pinterest/posts/{post_id}/schedule')
def unavailable(request: Request):
    require_same_origin(request)
    raise HTTPException(403, drafts.APPROVAL_MESSAGE)

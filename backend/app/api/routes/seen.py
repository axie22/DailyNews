from fastapi import APIRouter
from pydantic import BaseModel

from app.seen_store import get_seen_ids, mark_seen, clear_seen

router = APIRouter(prefix="/api/seen", tags=["seen"])


class MarkSeenRequest(BaseModel):
    ids: list[str]


@router.get("")
def get_seen():
    return {"seen_ids": get_seen_ids()}


@router.post("")
def post_seen(body: MarkSeenRequest):
    merged = mark_seen(body.ids)
    return {"seen_ids": merged, "count": len(merged)}


@router.delete("")
def delete_seen():
    clear_seen()
    return {"ok": True}

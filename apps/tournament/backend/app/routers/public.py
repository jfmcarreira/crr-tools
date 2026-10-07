from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from ..services.state import get_public_state
from .dependencies import DB

router = APIRouter(prefix="/api/public")


@router.get("/state")
@router.head("/state", include_in_schema=False)
def state(db: DB):
    return get_public_state(db)


@router.get("/events")
@router.head("/events", include_in_schema=False)
async def events(request: Request):
    return StreamingResponse(request.app.state.events.stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache, no-transform", "Connection": "keep-alive", "X-Accel-Buffering": "no"})

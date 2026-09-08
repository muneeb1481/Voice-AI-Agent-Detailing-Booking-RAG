from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import CallTranscript
from app.schemas import CallTranscriptOut
from app.security import current_admin

router = APIRouter(prefix="/api/call-transcripts", tags=["call-transcripts"])


@router.get("", response_model=list[CallTranscriptOut])
def list_call_transcripts(
    db: Session = Depends(get_db), _: str = Depends(current_admin)
) -> list[CallTranscript]:
    return list(
        db.execute(select(CallTranscript).order_by(CallTranscript.created_at.desc()))
        .scalars()
        .all()
    )

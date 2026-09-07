from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Detailer
from app.schemas import DetailerCreate, DetailerOut
from app.security import current_admin

router = APIRouter(prefix="/api/detailers", tags=["detailers"])


@router.get("", response_model=list[DetailerOut])
def list_detailers(
    db: Session = Depends(get_db), _: str = Depends(current_admin)
) -> list[Detailer]:
    return list(
        db.execute(select(Detailer).where(Detailer.active).order_by(Detailer.name))
        .scalars()
        .all()
    )


@router.post("", response_model=DetailerOut, status_code=status.HTTP_201_CREATED)
def create_detailer(
    payload: DetailerCreate, db: Session = Depends(get_db), _: str = Depends(current_admin)
) -> Detailer:
    name = payload.name.strip()
    existing = db.execute(select(Detailer).where(Detailer.name == name)).scalar_one_or_none()
    if existing:
        if not existing.active:
            existing.active = True
            db.commit()
            db.refresh(existing)
        return existing
    detailer = Detailer(name=name)
    db.add(detailer)
    db.commit()
    db.refresh(detailer)
    return detailer


@router.delete("/{detailer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_detailer(
    detailer_id: str, db: Session = Depends(get_db), _: str = Depends(current_admin)
) -> None:
    detailer = db.get(Detailer, detailer_id)
    if detailer is None:
        raise HTTPException(status_code=404, detail="Detailer not found")
    # Soft delete: existing bookings keep their (denormalized, free-text) detailer
    # name regardless — this only removes them from future dropdown choices.
    detailer.active = False
    db.commit()

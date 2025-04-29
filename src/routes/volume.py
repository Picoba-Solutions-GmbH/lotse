import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.models.database_access import get_db_session
from src.services.volume_repository import VolumeRepository

router = APIRouter(prefix="/volumes", tags=["volumes"])


class VolumeCreate(BaseModel):
    name: str
    pvc_name: str


class VolumeUpdate(BaseModel):
    name: Optional[str] = None
    pvc_name: Optional[str] = None


class VolumeResponse(BaseModel):
    id: str
    name: str
    pvc_name: str

    class Config:
        from_attributes = True


@router.post("/", response_model=VolumeResponse)
async def create_volume(
    volume: VolumeCreate,
    db: Session = Depends(get_db_session)
):
    volume_id = str(uuid.uuid4())
    return VolumeRepository.create_volume(
        db,
        volume_id=volume_id,
        name=volume.name,
        pvc_name=volume.pvc_name
    )


@router.get("/", response_model=List[VolumeResponse])
async def list_volumes(
    db: Session = Depends(get_db_session)
):
    return VolumeRepository.list_volumes(db)


@router.get("/{volume_id}", response_model=VolumeResponse)
async def get_volume(
    volume_id: str,
    db: Session = Depends(get_db_session)
):
    volume = VolumeRepository.get_volume(db, volume_id)
    if not volume:
        raise HTTPException(status_code=404, detail="Volume not found")
    return volume


@router.put("/{volume_id}", response_model=VolumeResponse)
async def update_volume(
    volume_id: str,
    volume: VolumeUpdate,
    db: Session = Depends(get_db_session)
):
    updated_volume = VolumeRepository.update_volume(
        db,
        volume_id=volume_id,
        name=volume.name,
        pvc_name=volume.pvc_name
    )
    if not updated_volume:
        raise HTTPException(status_code=404, detail="Volume not found")
    return updated_volume


@router.delete("/{volume_id}")
async def delete_volume(
    volume_id: str,
    db: Session = Depends(get_db_session)
):
    success = VolumeRepository.delete_volume(db, volume_id)
    if not success:
        raise HTTPException(status_code=404, detail="Volume not found")
    return {"message": "Volume deleted successfully"}

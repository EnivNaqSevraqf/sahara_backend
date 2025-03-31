from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session
from typing import List
from database.db import get_db
from models.announcement import Announcement
from dependencies.auth import prof_or_ta_required, prof_required
from pydantic import BaseModel
from datetime import datetime

router = APIRouter(
    prefix="/api/announcements",
    tags=["API Announcements"]
)

class AnnouncementBase(BaseModel):
    title: str
    content: str
    creator_id: int
    url_name: str = None

class AnnouncementCreate(AnnouncementBase):
    pass

class AnnouncementResponse(AnnouncementBase):
    id: int
    created_at: datetime
    creator_name: str

    class Config:
        orm_mode = True

@router.get("/")
async def get_all_announcements(db: Session = Depends(get_db)):
    """
    Get all announcements through API
    """
    announcements = db.query(Announcement).all()
    return announcements

@router.get("/{announcement_id}")
async def get_announcement(announcement_id: int, db: Session = Depends(get_db)):
    """
    Get a specific announcement through API
    """
    announcement = db.query(Announcement).filter(Announcement.id == announcement_id).first()
    if not announcement:
        raise HTTPException(status_code=404, detail="Announcement not found")
    return announcement

@router.post("/create")
async def create_announcement(
    announcement: AnnouncementCreate,
    db: Session = Depends(get_db),
    token: str = Depends(prof_or_ta_required)
):
    """
    Create a new announcement through API
    """
    db_announcement = Announcement(
        title=announcement.title,
        content=announcement.content,
        creator_id=announcement.creator_id,
        url_name=announcement.url_name
    )
    db.add(db_announcement)
    db.commit()
    db.refresh(db_announcement)
    return db_announcement

@router.put("/{announcement_id}")
async def update_announcement(
    announcement_id: int,
    announcement: AnnouncementBase,
    db: Session = Depends(get_db),
    token: str = Depends(prof_or_ta_required)
):
    """
    Update an announcement through API
    """
    db_announcement = db.query(Announcement).filter(Announcement.id == announcement_id).first()
    if not db_announcement:
        raise HTTPException(status_code=404, detail="Announcement not found")
    
    for key, value in announcement.dict().items():
        setattr(db_announcement, key, value)
    
    db.commit()
    db.refresh(db_announcement)
    return db_announcement

@router.delete("/{announcement_id}")
async def delete_announcement(
    announcement_id: int,
    db: Session = Depends(get_db),
    token: str = Depends(prof_required)
):
    """
    Delete an announcement through API
    """
    announcement = db.query(Announcement).filter(Announcement.id == announcement_id).first()
    if not announcement:
        raise HTTPException(status_code=404, detail="Announcement not found")
    db.delete(announcement)
    db.commit()
    return {"message": "Announcement deleted successfully"} 
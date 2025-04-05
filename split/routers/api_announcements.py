import os
import uuid
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form as FastAPIForm
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timezone
from ..database.db import get_db
from ..models.announcement import Announcement
from ..models.user import User
from ..dependencies.auth import get_current_user
from pydantic import BaseModel

class Show(BaseModel):
    id: int
    creator_id: int
    created_at: str
    title: str
    content: str  # Contains Markdown formatted text
    url_name: Optional[str] = None
    creator_name: Optional[str] = None

    class Config:
        orm_mode = True

router = APIRouter(
    prefix="/announcements",
    tags=["API Announcements"]
)

@router.post('/', status_code=status.HTTP_201_CREATED)
async def create(
    title: str = FastAPIForm(...),
    description: str = FastAPIForm(...),
    file: UploadFile = File(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    print(f"DEBUG: POST / route called - title: {title}, description length: {len(description)}")
    print(f"DEBUG: Request file: {file.filename if file else 'No file'}")
    print(f"DEBUG: Current user role: {current_user['role'].value}")
    try:
        # Check if user is professor
        if current_user["role"].value != "prof":
            print(f"DEBUG: Permission denied - user role: {current_user['role'].value}")
            raise HTTPException(
                status_code=403,
                detail="Only professors can create announcements"
            )
            
        user = current_user["user"]
        print(f"DEBUG: User ID: {user.id}, Username: {user.username}")
        # Create announcement
        announcement = Announcement(
            title=title,
            content=description,
            creator_id=user.id,
            created_at=datetime.now(timezone.utc).isoformat()
        )
        print(f"DEBUG: Created announcement object with title: {title}")


        # Handle file upload if provided
        if file:
            # Validate file size (50MB limit)
            if file.size > 50 * 1024 * 1024:
                raise HTTPException(
                    status_code=400,
                    detail="File size must be less than 50MB"
                )

            # Validate file type
            allowed_types = ['application/pdf', 'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'image/jpeg', 'image/png']
            if file.content_type not in allowed_types:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid file type. Please upload a PDF, Word document, or image (JPEG/PNG)"
                )

            # Generate unique filename
            file_extension = os.path.splitext(file.filename)[1]
            unique_filename = f"{uuid.uuid4()}{file_extension}"
            
            # Save file
            file_path = os.path.join("uploads", unique_filename)
            with open(file_path, "wb") as buffer:
                content = await file.read()
                buffer.write(content)
            
            announcement.url_name = unique_filename

        db.add(announcement)
        db.commit()
        db.refresh(announcement)


        return announcement
    except HTTPException as e:
        raise e
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.get('/{id}/download')
async def download_announcement_file(
    id: int,
    db: Session = Depends(get_db)
):
    try:
        announcement = db.query(Announcement).filter(Announcement.id == id).first()
        if not announcement or not announcement.url_name:
            raise HTTPException(status_code=404, detail="File not found")
        
        file_path = os.path.join("uploads", announcement.url_name)
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="File not found")
        
        # Determine content type based on file extension
        file_extension = os.path.splitext(announcement.url_name)[1].lower()
        content_type = {
            '.pdf': 'application/pdf',
            '.doc': 'application/msword',
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.txt': 'text/plain'
        }.get(file_extension, 'application/octet-stream')
        
        return FileResponse(
            file_path,
            filename=announcement.url_name,
            media_type=content_type,
            headers={
                "Content-Disposition": f'attachment; filename="{announcement.url_name}"'
            }
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get('/', response_model=List[Show])
def all(db: Session = Depends(get_db)):
    try:
        announcements = db.query(Announcement).order_by(Announcement.created_at.desc()).all()
        # Instead of returning creator id return creator name
        for announcement in announcements:
            creator = db.query(User).filter(User.id == announcement.creator_id).first()
            announcement.creator_name = creator.name if creator else f"User {announcement.creator_id}"
        return announcements
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get('/{id}', status_code=200, response_model=Show)
def show(id: int, db: Session = Depends(get_db)):
    try:
        announcement = db.query(Announcement).filter(Announcement.id == id).first()
        if not announcement:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f'Announcement with id {id} not found')
        return announcement
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error fetching announcement")

@router.delete('/{id}', status_code=status.HTTP_204_NO_CONTENT)
def destroy(
    id: int, 
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
       
        if current_user["role"].value != "prof":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only professors can delete announcements")
        
        announcement = db.query(Announcement).filter(Announcement.id == id).first()
        if not announcement:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f'Announcement with id: {id} not found')
        
        # Delete the associated file if it exists
        if announcement.url_name:
            file_path = os.path.join("uploads", announcement.url_name)
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except OSError:
                    pass  # Ignore file deletion errors during cleanup
        
        # Delete the announcement from database
        db.delete(announcement)
        db.commit()
        
        return {'message': 'Announcement deleted successfully'}
    except HTTPException as e:
        db.rollback()
        raise e
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error deleting announcement: {str(e)}")
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session
from typing import List
from ..database.db import get_db
from ..dependencies.auth import prof_or_ta_required, prof_required
from pydantic import BaseModel
import os
import uuid
from datetime import datetime

# this whole file is not used currently.
router = APIRouter(
    prefix="/api/files",
    tags=["API Files"]
)

UPLOAD_DIR = "uploads"
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

class FileResponse(BaseModel):
    filename: str
    file_url: str
    uploaded_at: datetime

@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    token: str = Depends(prof_or_ta_required)
):
    """
    Upload a file through API
    """
    # Generate unique filename
    file_extension = os.path.splitext(file.filename)[1]
    unique_filename = f"{uuid.uuid4()}{file_extension}"
    
    # Save file
    file_path = os.path.join(UPLOAD_DIR, unique_filename)
    with open(file_path, "wb") as buffer:
        content = await file.read()
        buffer.write(content)
    
    # Return file information
    return {
        "filename": file.filename,
        "file_url": f"/files/{unique_filename}",
        "uploaded_at": datetime.now()
    }

@router.get("/download/{filename}")
async def download_file(filename: str):
    """
    Download a file through API
    """
    file_path = os.path.join(UPLOAD_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found"
        )
    return {"file_url": f"/files/{filename}"}

@router.delete("/{filename}")
async def delete_file(
    filename: str,
    db: Session = Depends(get_db),
    token: str = Depends(prof_required)
):
    """
    Delete a file through API
    """
    file_path = os.path.join(UPLOAD_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found"
        )
    os.remove(file_path)
    return {"message": "File deleted successfully"} 
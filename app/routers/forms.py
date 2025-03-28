from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime, timezone

from app.db.session import get_db
from app.core.security.auth import get_current_user
from app.models.user import User, RoleType
from app.services.file_storage import file_storage

router = APIRouter(prefix="/forms", tags=["forms"])

@router.post("/submit")
async def submit_form(
    form_data: dict,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        user = current_user["user"]
        
        # Validate form data
        if not form_data.get("form_type"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Form type is required"
            )

        # Process form based on type
        if form_data["form_type"] == "feedback":
            return await process_feedback_form(form_data, user, db)
        elif form_data["form_type"] == "submission":
            return await process_submission_form(form_data, user, db)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown form type: {form_data['form_type']}"
            )
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

async def process_feedback_form(form_data: dict, user: User, db: Session):
    # Validate feedback specific fields
    required_fields = ["team_id", "feedback_type", "rating", "comments"]
    for field in required_fields:
        if field not in form_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Missing required field: {field}"
            )
    
    # Additional processing for feedback forms
    # Implementation would go here based on specific requirements
    return {"message": "Feedback submitted successfully"}

async def process_submission_form(form_data: dict, user: User, db: Session):
    # Validate submission specific fields
    if "files" not in form_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No files provided for submission"
        )
    
    # Process file uploads
    uploaded_files = []
    for file in form_data["files"]:
        success, result = await file_storage.save_file(
            file,
            subfolder=f"submissions/{user.id}"
        )
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to upload file: {result}"
            )
        uploaded_files.append(result)
    
    return {
        "message": "Submission successful",
        "files": uploaded_files
    }
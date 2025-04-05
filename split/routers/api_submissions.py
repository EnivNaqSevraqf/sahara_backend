from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form as FastAPIForm

from sqlalchemy.orm import Session
from typing import List
from ..database.db import get_db
from ..models.submission import Submission
from ..models.gradeables import Gradeable
from ..models.user import User
from ..dependencies.auth import prof_or_ta_required, prof_required, get_current_user
from pydantic import BaseModel
from datetime import datetime
from fastapi.responses import FileResponse, JSONResponse
import os
from ..models.roles import RoleType
from ..models.submittable import Submittable

router = APIRouter(
    prefix="",
    tags=["API Submissions"]
)


@router.get("/submissions/{submission_id}/download")
async def download_submission(
    submission_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Download a submission file"""
    try:
        submission = db.query(Submission).filter(Submission.id == submission_id).first()
        if not submission:
            raise HTTPException(status_code=404, detail="Submission not found")
        
        user = current_user["user"]
        role = current_user["role"]
        
        # Check permissions
        if role == RoleType.PROF or role == RoleType.TA:
            # Professors can download any submission
            pass
        elif role == RoleType.STUDENT:
            # Students can only download their team's submission
            team = user.teams[0] if user.teams else None
            if not team.id or team.id != submission.team_id:
                raise HTTPException(status_code=403, detail="Not authorized to download this submission")
        else:
            raise HTTPException(status_code=403, detail="Not authorized to download submissions")
        
        # Get the file path
        local_path = submission.file_url.lstrip('/')
        if not os.path.exists(local_path):
            raise HTTPException(status_code=404, detail="File not found")
        
        # Return the file directly
        return FileResponse(
            local_path,
            filename=submission.original_filename,
            media_type="application/octet-stream"
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error downloading submission: {str(e)}")
    

@router.delete("/submissions/{submission_id}")
async def delete_submission(
    submission_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Delete a submission (professors or the submitting student)"""
    try:
        submission = db.query(Submission).filter(Submission.id == submission_id).first()
        if not submission:
            raise HTTPException(status_code=404, detail="Submission not found")
        
        # Check if user is professor or the student who submitted
        user = current_user["user"]
        team = user.teams[0] if user.teams else None
        if current_user["role"] == RoleType.STUDENT:
            # For students, check if they belong to the team that submitted
            if team.id != submission.team_id:
                raise HTTPException(status_code=403, detail="You can only delete your own submissions")
        
        # Delete the submission file if it exists
        if submission.file_url:
            local_path = submission.file_url.lstrip('/')
            if os.path.exists(local_path):
                os.remove(local_path)
        
        # Delete the submission record
        db.delete(submission)
        db.commit()
        
        return JSONResponse(status_code=200, content={"message": "Submission deleted successfully"})
    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    
@router.put("/submissions/{submission_id}/grade")
async def grade_submission(
    submission_id: int,
    score: int = FastAPIForm(...),
    db: Session = Depends(get_db),
    token: str = Depends(prof_or_ta_required)
):
    """Grade a submission (professors only)"""
    try:
        # Get the submission
        submission = db.query(Submission).filter(Submission.id == submission_id).first()
        if not submission:
            raise HTTPException(status_code=404, detail="Submission not found")
        
        # Get the submittable to check max score
        submittable = db.query(Submittable).filter(Submittable.id == submission.submittable_id).first()
        if not submittable:
            raise HTTPException(status_code=404, detail="Submittable not found")
        
        # Validate score
        if score < 0:
            raise HTTPException(status_code=400, detail="Score cannot be negative")
        if score > submittable.max_score:
            raise HTTPException(
                status_code=400, 
                detail=f"Score cannot exceed maximum score of {submittable.max_score}"
            )
        
        # Update the submission score
        submission.score = score
        db.commit()
        
        return JSONResponse(status_code=200, content={
            "message": "Submission graded successfully",
            "submission_id": submission.id,
            "score": submission.score,
            "max_score": submittable.max_score
        })
    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error grading submission: {str(e)}")

from fastapi import APIRouter, Depends, HTTPException, status, Form as FastAPIForm
from sqlalchemy.orm import Session
from typing import List
from ..database.db import get_db
from ..models.user import User
from ..models.roles import RoleType
from ..models.assignment import Assignment
from ..models.assignable import Assignable
from ..dependencies.auth import prof_or_ta_required, prof_required, get_current_user
from fastapi.responses import FileResponse, JSONResponse
import os

router = APIRouter(
    prefix="",
    tags=["API Assignments"]
)




@router.get("/assignments/{assignment_id}/download")
async def download_assignment(
    assignment_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Download a submission file"""
    try:
        assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
        if not assignment:
            raise HTTPException(status_code=404, detail="Assignment not found")
        
        user = current_user["user"]
        role = current_user["role"]
        
        # Check permissions
        if role == RoleType.PROF or role == RoleType.TA:
            # Professors can download any submission
            pass
        elif role == RoleType.STUDENT:
            # Students can only download their submission
            if not user.id or user.id != assignment.user_id:
                raise HTTPException(status_code=403, detail="Not authorized to download this submission")
        else:
            raise HTTPException(status_code=403, detail="Not authorized to download submissions")
        
        # Get the file path
        local_path = assignment.file_url.lstrip('/')
        if not os.path.exists(local_path):
            raise HTTPException(status_code=404, detail="File not found")
        
        # Return the file directly
        return FileResponse(
            local_path,
            filename=assignment.original_filename,
            media_type="application/octet-stream"
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error downloading submission: {str(e)}")
    


@router.delete("/assignments/{assignment_id}")
async def delete_assignment(
    assignment_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Delete a submission (professors or the submitting student)"""
    try:
        assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
        if not assignment:
            raise HTTPException(status_code=404, detail="Assignment not found")
        
        # Check if user is professor or the student who submitted
        user = current_user["user"]
        if current_user["role"] == RoleType.STUDENT:
            # For students, check if they belong to the team that submitted
            if user.id != assignment.user_id:
                raise HTTPException(status_code=403, detail="You can only delete your own submissions")
        
        # Delete the submission file if it exists
        if assignment.file_url:
            local_path = assignment.file_url.lstrip('/')
            if os.path.exists(local_path):
                os.remove(local_path)
        
        # Delete the submission record
        db.delete(assignment)
        db.commit()
        
        return JSONResponse(status_code=200, content={"message": "Assignment deleted successfully"})
    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error deleting assignment: {str(e)}")
    
# this is to grade a assignment, done by profs
@router.put("/assignments/{assignment_id}/grade")
async def grade_assignment(
    assignment_id: int,
    score: int = FastAPIForm(...),
    db: Session = Depends(get_db),
    token: str = Depends(prof_or_ta_required)
):
    """Grade a submission (professors only)"""
    try:
        # Get the submission
        assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
        if not assignment:
            raise HTTPException(status_code=404, detail="Assignment not found")
        
        # Get the submittable to check max score
        assignable = db.query(Assignable).filter(Assignable.id == assignment.assignable_id).first()
        if not assignable:
            raise HTTPException(status_code=404, detail="Assignable not found")
        
        # Validate score
        if score < 0:
            raise HTTPException(status_code=400, detail="Score cannot be negative")
        if score > assignable.max_score:
            raise HTTPException(
                status_code=400, 
                detail=f"Score cannot exceed maximum score of {assignable.max_score}"
            )
        
        # Update the submission score
        assignment.score = score
        db.commit()
        
        return JSONResponse(status_code=200, content={
            "message": "Submission graded successfully",
            "assignment_id": assignment.id,
            "score": assignment.score,
            "max_score": assignable.max_score
        })
    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error grading assignment: {str(e)}")
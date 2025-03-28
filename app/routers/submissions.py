from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timezone

from app.db.session import get_db
from app.core.security.auth import get_current_user
from app.models.user import User, RoleType
from app.models.submission import Submission
from app.services.file_storage import file_storage
from app.utils.helpers import get_utc_now, paginate_results

router = APIRouter(prefix="/submissions", tags=["submissions"])

@router.post("/upload")
async def upload_submission(
    assignment_id: int,
    files: List[UploadFile] = File(...),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        user = current_user["user"]
        
        # Validate files
        if not files:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No files provided"
            )

        # Process and save each file
        uploaded_files = []
        for file in files:
            success, result = await file_storage.save_file(
                file,
                subfolder=f"assignments/{assignment_id}/{user.id}"
            )
            if not success:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Failed to upload file: {result}"
                )
            uploaded_files.append(result)

        # Record submission in database
        submission = Submission(
            assignment_id=assignment_id,
            team_id=user.team_id,
            submitted_at=get_utc_now(),
            files=uploaded_files
        )
        db.add(submission)
        db.commit()
        db.refresh(submission)

        return {
            "message": "Submission uploaded successfully",
            "submission_id": submission.id,
            "files": uploaded_files
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.get("/team/{team_id}")
async def get_team_submissions(
    team_id: int,
    page: int = 1,
    page_size: int = 10,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        user = current_user["user"]
        
        # Verify access rights
        if user.role.role == RoleType.STUDENT and user.team_id != team_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only view submissions for your own team"
            )

        # Get submissions
        submissions = (
            db.query(Submission)
            .filter(Submission.team_id == team_id)
            .order_by(Submission.submitted_at.desc())
            .all()
        )

        # Format submission data
        submission_data = []
        for submission in submissions:
            submission_data.append({
                "id": submission.id,
                "assignment_id": submission.assignment_id,
                "submitted_at": submission.submitted_at.isoformat(),
                "files": submission.files,
                "grade": submission.grade,
                "feedback": submission.feedback
            })

        # Paginate results
        return paginate_results(submission_data, page, page_size)
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.post("/{submission_id}/grade")
async def grade_submission(
    submission_id: int,
    grade: float,
    feedback: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        if current_user["role"] not in [RoleType.PROF, RoleType.TA]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only professors and TAs can grade submissions"
            )

        submission = db.query(Submission).filter(
            Submission.id == submission_id
        ).first()

        if not submission:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Submission not found"
            )

        # Update grade and feedback
        submission.grade = grade
        submission.feedback = feedback
        submission.graded_by = current_user["user"].id
        submission.graded_at = get_utc_now()

        db.commit()
        db.refresh(submission)

        return {
            "message": "Submission graded successfully",
            "submission_id": submission_id,
            "grade": grade,
            "feedback": feedback
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
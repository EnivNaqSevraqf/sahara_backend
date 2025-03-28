from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime, timezone

from app.db.session import get_db
from app.models.feedback import FeedbackSubmission, FeedbackDetail
from app.models.user import User, RoleType
from app.core.security.auth import get_current_user
from app.schemas.feedback import FeedbackSubmissionRequest

router = APIRouter(tags=["feedback"])

@router.get("/students")
async def get_student_feedback_info(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        user = current_user["user"]
        
        if current_user["role"] != RoleType.STUDENT:
            raise HTTPException(
                status_code=403,
                detail="Only students can access this endpoint"
            )

        if not user.teams:
            raise HTTPException(
                status_code=404,
                detail="You have not been assigned to a team"
            )
            
        team = user.teams[0]

        team_members = [
            {
                "id": member.id,
                "name": member.name,
                "is_current_user": member.id == user.id
            }
            for member in team.members
        ]

        if len(team_members) <= 1:
            raise HTTPException(
                status_code=400,
                detail="No team members found to provide feedback for"
            )

        existing_submission = db.query(FeedbackSubmission).filter(
            FeedbackSubmission.submitter_id == user.id,
            FeedbackSubmission.team_id == team.id
        ).first()

        submitted_feedback = None
        if existing_submission:
            feedback_details = db.query(FeedbackDetail).filter(
                FeedbackDetail.submission_id == existing_submission.id
            ).all()
            
            submitted_feedback = {
                "submission_id": existing_submission.id,
                "submitted_at": existing_submission.submitted_at.isoformat(),
                "details": [
                    {
                        "member_id": detail.member_id,
                        "contribution": detail.contribution,
                        "remarks": detail.remarks
                    }
                    for detail in feedback_details
                ]
            }

        return {
            "team_id": team.id,
            "team_name": team.name,
            "members": team_members,
            "submitted_feedback": submitted_feedback
        }
        
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/submit")
async def submit_student_feedback(
    feedback: FeedbackSubmissionRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        user = current_user["user"]
        
        if current_user["role"] != RoleType.STUDENT:
            raise HTTPException(
                status_code=403,
                detail="Only students can submit feedback"
            )

        if not any(team.id == feedback.team_id for team in user.teams):
            raise HTTPException(
                status_code=403,
                detail="You can only submit feedback for your own team"
            )

        existing_submission = db.query(FeedbackSubmission).filter(
            FeedbackSubmission.submitter_id == user.id,
            FeedbackSubmission.team_id == feedback.team_id
        ).first()

        if existing_submission:
            raise HTTPException(
                status_code=400,
                detail="You have already submitted feedback for this team"
            )

        team = next(team for team in user.teams if team.id == feedback.team_id)
        expected_member_count = len(team.members)
        if len(feedback.details) != expected_member_count:
            raise HTTPException(
                status_code=400,
                detail="Feedback must be provided for all team members"
            )

        team_member_ids = {member.id for member in team.members}
        submitted_member_ids = {detail.member_id for detail in feedback.details}
        if team_member_ids != submitted_member_ids:
            raise HTTPException(
                status_code=400,
                detail="Feedback can only be provided for current team members"
            )

        total_contribution = sum(detail.contribution for detail in feedback.details)
        if total_contribution != 100:
            raise HTTPException(
                status_code=400,
                detail="Total contribution must equal 100%"
            )

        new_submission = FeedbackSubmission(
            submitter_id=user.id,
            team_id=feedback.team_id,
            submitted_at=datetime.now(timezone.utc)
        )
        db.add(new_submission)
        db.flush()

        for detail in feedback.details:
            new_detail = FeedbackDetail(
                submission_id=new_submission.id,
                member_id=detail.member_id,
                contribution=detail.contribution,
                remarks=detail.remarks
            )
            db.add(new_detail)

        db.commit()
        return {"message": "Feedback submitted successfully"}
    except HTTPException as he:
        db.rollback()
        raise he
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/admin")
async def get_admin_feedback(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        if current_user["role"] not in [RoleType.TA, RoleType.PROF]:
            raise HTTPException(
                status_code=403,
                detail="Only teaching assistants and professors can access this endpoint"
            )

        teams_with_feedback = (
            db.query(Team)
            .join(FeedbackSubmission, Team.id == FeedbackSubmission.team_id)
            .distinct()
            .all()
        )

        result = []
        for team in teams_with_feedback:
            submission_count = (
                db.query(FeedbackSubmission)
                .filter(FeedbackSubmission.team_id == team.id)
                .count()
            )

            result.append({
                "team_id": team.id,
                "team_name": team.name,
                "member_count": len(team.members),
                "submission_count": submission_count,
                "last_submission": db.query(FeedbackSubmission)
                    .filter(FeedbackSubmission.team_id == team.id)
                    .order_by(FeedbackSubmission.submitted_at.desc())
                    .first()
                    .submitted_at.isoformat()
            })

        return result
        
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
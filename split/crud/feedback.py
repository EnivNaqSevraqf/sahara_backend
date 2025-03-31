from sqlalchemy.orm import Session
from ..models.feedback_submission import FeedbackSubmission
from ..models.feedback_detail import FeedbackDetail
from ..models.user import User

def get_student_feedback_info(current_user: User, db: Session):
    submissions = db.query(FeedbackSubmission).filter(
        FeedbackSubmission.submitter_id == current_user.id
    ).all()
    return submissions

def get_admin_feedback(current_user: User, db: Session):
    submissions = db.query(FeedbackSubmission).all()
    return submissions

def get_team_feedback_details(team_id: int, current_user: User, db: Session):
    submission = db.query(FeedbackSubmission).filter(
        FeedbackSubmission.team_id == team_id
    ).first()
    if not submission:
        return None
    return submission 
from sqlalchemy.orm import Session
from ..models.submittable import Submittable
from ..models.submission import Submission

def get_submittables(db: Session):
    submittables = db.query(Submittable).all()
    return submittables

def get_all_submittables(db: Session):
    submittables = db.query(Submittable).all()
    return submittables

def get_submittable(submittable_id: int, db: Session):
    submittable = db.query(Submittable).filter(Submittable.id == submittable_id).first()
    if not submittable:
        return None
    return submittable

def get_submittable_submissions(submittable_id: int, db: Session):
    submissions = db.query(Submission).filter(Submission.submittable_id == submittable_id).all()
    return submissions 
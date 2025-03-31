from sqlalchemy.orm import Session
from ..models.assignable import Assignable
from ..models.assignment import Assignment

def get_assignables(db: Session):
    assignables = db.query(Assignable).all()
    return assignables

def get_assignable(assignable_id: int, db: Session):
    assignable = db.query(Assignable).filter(Assignable.id == assignable_id).first()
    if not assignable:
        return None
    return assignable

def get_assignable_assignments(assignable_id: int, db: Session):
    assignments = db.query(Assignment).filter(Assignment.assignable_id == assignable_id).all()
    return assignments 
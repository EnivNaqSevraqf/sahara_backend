from sqlalchemy.orm import Session
from app.models.user import Role, RoleType

def init_db(db: Session) -> None:
    """Initialize database with required data"""
    # Create roles if they don't exist
    for role_type in RoleType:
        existing_role = db.query(Role).filter(Role.role == role_type).first()
        if not existing_role:
            new_role = Role(role=role_type)
            db.add(new_role)
    
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise e
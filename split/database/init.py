from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from ..config.config import DATABASE_URL
from ..models.user import User
from ..models.roles import Role, RoleType
from ..dependencies.auth import pwd_context
from ..config.config import SessionLocal


Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def create_default_roles():
    with SessionLocal() as db:
        for role_type in RoleType:
            existing_role = db.query(Role).filter(Role.role == role_type).first()
            if not existing_role:
                new_role = Role(role=role_type)
                db.add(new_role)
        db.commit()

# Create default admin/prof user
def create_default_admin():
    with SessionLocal() as db:
        prof_role = db.query(Role).filter(Role.role == RoleType.PROF).first()
        if not prof_role:
            return  # Can't create user without role
        
        existing_admin = db.query(User).filter(User.username == "root123").first()
        if not existing_admin:
            new_admin = User(
                name="Root Admin",
                email="root@example.com",
                username="root123",
                hashed_password=pwd_context.hash("root123"),
                role_id=prof_role.id
            )
            db.add(new_admin)
            db.commit()




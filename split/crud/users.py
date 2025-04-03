from sqlalchemy.orm import Session
from ..models.user import User
from ..models.user import Professor
from ..models.user import TA
from ..models.user import Student
from ..models.user import UserPreferences
from ..models.roles import Role
from fastapi import HTTPException
from passlib.context import CryptContext
from datetime import datetime, timedelta
import jwt
from typing import Optional
from ..utils.auth import verify_password, create_hashed_password
# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT settings
SECRET_KEY = "your-secret-key"  # Move to config
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30



def get_people(db: Session):
    users = db.query(User).all()
    return users

def get_user_data(token: str, db: Session):
    user = db.query(User).filter(User.username == token).first()
    return user

def get_user(db: Session, user_id: int):
    return db.query(User).filter(User.id == user_id).first()

def get_professor(db: Session, professor_id: int):
    return db.query(Professor).filter(Professor.id == professor_id).first()

def get_ta(db: Session, ta_id: int):
    return db.query(TA).filter(TA.id == ta_id).first()

def get_student(db: Session, student_id: int):
    return db.query(Student).filter(Student.id == student_id).first()

def get_user_preferences(db: Session, user_preferences_id: int):
    return db.query(UserPreferences).filter(UserPreferences.id == user_preferences_id).first()

def get_user_by_email(db: Session, email: str):
    return db.query(User).filter(User.email == email).first()

def get_user_by_username(db: Session, username: str):
    return db.query(User).filter(User.username == username).first()

def create_user(db: Session, user_data: dict):
    user = User(**user_data)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

def create_professor(db: Session, professor_data: dict):
    professor = Professor(**professor_data)
    db.add(professor)
    db.commit()
    db.refresh(professor)
    return professor

def create_ta(db: Session, ta_data: dict):
    # Create role if it doesn't exist
    role = db.query(Role).filter(Role.name == "ta").first()
    if not role:
        role = Role(name="ta")
        db.add(role)
        db.commit()
        db.refresh(role)
    
    # Create TA user
    ta_data["role_id"] = role.id
    ta_data["password"] = create_hashed_password(ta_data["password"])
    return create_user(db, ta_data)

def create_student(db: Session, student_data: dict):
    # Create role if it doesn't exist
    role = db.query(Role).filter(Role.name == "student").first()
    if not role:
        role = Role(name="student")
        db.add(role)
        db.commit()
        db.refresh(role)
    
    # Create student user
    student_data["role_id"] = role.id
    student_data["password"] = create_hashed_password(student_data["password"])
    return create_user(db, student_data)

def create_user_preferences(db: Session, user_preferences_data: dict):
    user_preferences = UserPreferences(**user_preferences_data)
    db.add(user_preferences)
    db.commit()
    db.refresh(user_preferences)
    return user_preferences

def update_user(db: Session, user_id: int, user_data: dict):
    user = get_user(db, user_id)
    if user:
        for key, value in user_data.items():
            setattr(user, key, value)
        db.commit()
        db.refresh(user)
    return user

def update_professor(db: Session, professor_id: int, professor_data: dict):
    professor = get_professor(db, professor_id)
    if professor:
        for key, value in professor_data.items():
            setattr(professor, key, value)
        db.commit()
        db.refresh(professor)
    return professor

def update_ta(db: Session, ta_id: int, ta_data: dict):
    ta = get_ta(db, ta_id)
    if ta:
        for key, value in ta_data.items():
            setattr(ta, key, value)
        db.commit()
        db.refresh(ta)
    return ta

def update_student(db: Session, student_id: int, student_data: dict):
    student = get_student(db, student_id)
    if student:
        for key, value in student_data.items():
            setattr(student, key, value)
        db.commit()
        db.refresh(student)
    return student

def update_user_preferences(db: Session, user_preferences_id: int, user_preferences_data: dict):
    user_preferences = get_user_preferences(db, user_preferences_id)
    if user_preferences:
        for key, value in user_preferences_data.items():
            setattr(user_preferences, key, value)
        db.commit()
        db.refresh(user_preferences)
    return user_preferences

def delete_user(db: Session, user_id: int):
    user = get_user(db, user_id)
    if user:
        db.delete(user)
        db.commit()
        return True
    return False

def delete_professor(db: Session, professor_id: int):
    professor = get_professor(db, professor_id)
    if professor:
        db.delete(professor)
        db.commit()
        return True
    return False

def delete_ta(db: Session, ta_id: int):
    ta = get_ta(db, ta_id)
    if ta:
        db.delete(ta)
        db.commit()
        return True
    return False

def delete_student(db: Session, student_id: int):
    student = get_student(db, student_id)
    if student:
        db.delete(student)
        db.commit()
        return True
    return False

def delete_user_preferences(db: Session, user_preferences_id: int):
    user_preferences = get_user_preferences(db, user_preferences_id)
    if user_preferences:
        db.delete(user_preferences)
        db.commit()
        return True
    return False

def create_prof(db: Session, prof_data: dict):
    # Create role if it doesn't exist
    role = db.query(Role).filter(Role.name == "professor").first()
    if not role:
        role = Role(name="professor")
        db.add(role)
        db.commit()
        db.refresh(role)
    
    # Create professor user
    prof_data["role_id"] = role.id
    prof_data["password"] = create_hashed_password(prof_data["password"])
    return create_user(db, prof_data)


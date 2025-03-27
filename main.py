import json
# Explicitly import FastAPI's Form and rename it to avoid conflicts
from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, Query, Header, Body, File, Form as FastAPIForm, WebSocket, WebSocketDisconnect, WebSocketException
from fastapi.responses import JSONResponse, Response, FileResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy import ForeignKey, create_engine, Column, Integer, String, Enum, Table, Text, DateTime, text
from sqlalchemy import ForeignKey, create_engine, Column, Integer, String, Enum, Table, Text, DateTime, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship, validates
from sqlalchemy.dialects.postgresql import JSONB, insert
from passlib.context import CryptContext
from datetime import datetime, timedelta
import jwt
import random
import string
from pydantic import BaseModel, EmailStr, validator
from typing import Annotated, List, Dict, Any, Optional
import enum
import secrets
import os
import tempfile
import io
from datetime import datetime, timezone
from fastapi.middleware.cors import CORSMiddleware
import traceback
from typing import Optional, List
import sys
import importlib.util
from typing import Optional, List, Annotated, Union
import shutil
import uuid
import json
import csv
from io import StringIO
from fastapi.staticfiles import StaticFiles
from typing import ForwardRef
import base64
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formatdate
import pandas as pd
# Create uploads directory if it doesn't exist
os.makedirs("uploads", exist_ok=True)

# Import CSV processing functions from authentication/read_csv.py
sys.path.append(os.path.join(os.path.dirname(__file__), 'authentication'))
from read_csv import extract_student_data_from_content, extract_ta_data_from_content, CSVFormatError


# Database setup - postgres
DATABASE_URL = "postgresql://avnadmin:AVNS_DkrVvzHCnOiMVJwagav@pg-8b6fabf-sahara-team-8.f.aivencloud.com:17950/defaultdb"
Base = declarative_base()

# Create engine
engine = create_engine(DATABASE_URL)

# Create session
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


####
# DEFINING ALL THE ORM CLASSES
####

class RoleType(enum.Enum):
    PROF = "prof"
    STUDENT = "student"
    TA = "ta"

class Role(Base):
    __tablename__ = "roles"
    id = Column(Integer, primary_key=True)
    role = Column(Enum(RoleType), nullable=False, unique=True)

    users = relationship("User", back_populates="role")

# Association table for User-Skills many-to-many relationship
user_skills = Table(
    "user_skills", Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id"), primary_key=True),
    Column("skill_id", Integer, ForeignKey("skills.id"), primary_key=True)
)
# Association table for Team-Skills many-to-many relationship
team_skills = Table(
    "team_skills", Base.metadata,
    Column("team_id", Integer, ForeignKey("teams.id"), primary_key=True),
    Column("skill_id", Integer, ForeignKey("skills.id"), primary_key=True)
)

class Skill(Base):
    __tablename__ = "skills"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    bgColor = Column(String, nullable=False)
    color = Column(String, nullable=False)
    icon = Column(String, nullable=False)
    
    # Relationship with users (TAs)
    users = relationship("User", secondary=user_skills, back_populates="skills")
    # Relationship with teams
    teams = relationship("Team", secondary=team_skills, back_populates="skills")

class Submittable(Base):
    __tablename__ = "submittables"
    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)  # Adding title field
    opens_at = Column(String, nullable=True)  # ISO 8601 format
    deadline = Column(String, nullable=False)  # ISO 8601 format
    description = Column(String, nullable=False)
    file_url = Column(String, nullable=False)  # URL path to the reference file
    original_filename = Column(String, nullable=False)
    max_score = Column(Integer, nullable=False)  # Maximum possible score for this submittable
    created_at = Column(String, default=datetime.now(timezone.utc).isoformat())
    creator_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    creator = relationship("User", back_populates="submittables")
    submissions = relationship("Submission", back_populates="submittable")

    @validates("creator_id")
    def validate_creator(self, key, value):
        with SessionLocal() as db:
            user = db.query(User).filter_by(id=value).first()
            if user and user.role.role != RoleType.PROF:
                raise ValueError("Only professors can create submittables.")
        return value

class Submission(Base):
    __tablename__ = "submissions"
    id = Column(Integer, primary_key=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    submitted_on = Column(String, default=datetime.now(timezone.utc).isoformat())
    file_url = Column(String, nullable=False)  # URL path to the reference file
    original_filename = Column(String, nullable=False)
    submittable_id = Column(Integer, ForeignKey("submittables.id"), nullable=False)
    score = Column(Integer, nullable=True)  # Score received for this submission

    team = relationship("Team", back_populates="submissions")
    submittable = relationship("Submittable", back_populates="submissions")

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    email = Column(String, nullable=False, unique=True)
    username = Column(String, nullable=False, unique=True)  # Added username field
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=False)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=True)
    hashed_password = Column(String, nullable=False)

    role = relationship("Role", back_populates="users")
    teams = relationship("Team", secondary="team_members", back_populates="members")
    responses = relationship("FormResponse", back_populates="user")
    gradeables = relationship("Gradeable", back_populates="creator")
    calendar_events = relationship("UserCalendarEvent", back_populates="creator")
    team_calendar_events = relationship("TeamCalendarEvent", back_populates="creator")
    # global_calendar_events = relationship("GlobalCalendarEvent", back_populates="creator")
    skills = relationship("Skill", secondary=user_skills, back_populates="users")
    gradeable_scores = relationship("GradeableScores", back_populates="user")
    submittables = relationship("Submittable", back_populates="creator", lazy="joined")
    messages = relationship("Message", back_populates="sender")
    
    @validates('skills')
    def validate_skills(self, key, skill):
        # Only allow TAs to have skills
        with SessionLocal() as db:
            role = db.query(Role).filter_by(id=self.role_id).first()
            if role and role.role != RoleType.TA:
                raise ValueError("Only TAs can have skills.")
        return skill

class Team(Base):
    __tablename__ = "teams"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    
    members = relationship("User", secondary="team_members", back_populates="teams")
    skills = relationship("Skill", secondary=team_skills, back_populates="teams")
    submissions = relationship("Submission", back_populates="team")

class Form(Base):
    __tablename__ = "forms"
    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    description = Column(String, nullable=True)
    created_at = Column(String, default=datetime.now(timezone.utc).isoformat())
    deadline = Column(String, nullable=False)  # ISO 8601 format
    form_json = Column(JSONB, nullable=False)

    # target_type = Column(Enum(RoleType), nullable=False)  # Role or Team
    # target_id = Column(Integer, nullable=False)  # Role ID or Team ID

    responses = relationship("FormResponse", back_populates="form")

    @validates("target_type", "target_id")
    def validate_target(self, key, value):
        if self.target_type == RoleType.ROLE:
            role = SessionLocal.query(Role).filter_by(id=self.target_id).first()
            if role and role.name == RoleType.PROFESSOR:
                raise ValueError("Forms cannot be assigned to Professors.")
        return value

team_members = Table(
    "team_members", Base.metadata,
    Column("team_id", Integer, ForeignKey("teams.id"), primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id"), primary_key=True)
)


class Announcement(Base):
    __tablename__ = "announcements"
    id = Column(Integer, primary_key=True)
    creator_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(String, default=datetime.now(timezone.utc).isoformat())
    title = Column(String, nullable=False)
    content = Column(String, nullable=False)  # Supports Markdown formatting for rich text
    url_name = Column(String, unique=True, nullable=True)
    
    @validates("creator_id")
    def validate_creator(self, key, value):
        with SessionLocal() as session:
            user = session.query(User).filter_by(id=value).first()
            if user and user.role == RoleType.STUDENT:
                raise ValueError("Students cannot create announcements.")
            return value


class FormResponse(Base):
    __tablename__ = "form_responses"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    form_id = Column(Integer, ForeignKey("forms.id"), nullable=False)
    submitted_at = Column(String, default=datetime.now(timezone.utc).isoformat())
    response_data = Column(String, nullable=False)  # JSON or serialized response data

    user = relationship("User", back_populates="responses")
    form = relationship("Form", back_populates="responses")


class Gradeable(Base):
    __tablename__ = "gradeables"
    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    description = Column(String, nullable=False)
    due_date = Column(String, nullable=False)
    max_points = Column(Integer, nullable=False)
    creator_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(String, default=datetime.now(timezone.utc).isoformat())

    creator = relationship("User", back_populates="gradeables")
    scores = relationship("GradeableScores", back_populates="gradeable")

    @validates("creator_id")
    def validate_creator(self, key, value):
        user = SessionLocal.query(User).filter_by(id=value).first()
        if user and user.role == RoleType.STUDENT:
            raise ValueError("Students cannot create gradeables.")
        return value
    
class GradeableScores(Base):
    __tablename__ = "gradeable_scores"
    id = Column(Integer, primary_key=True)
    gradeable_id = Column(Integer, ForeignKey("gradeables.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    score = Column(Integer, nullable=False)
    feedback = Column(String, nullable=True)

    gradeable = relationship("Gradeable", back_populates="scores")
    user = relationship("User", back_populates="gradeable_scores")

class GlobalCalendarEvent(Base):
    __tablename__ = "global_calendar_events"
    id = Column(Integer, primary_key=True)
    events = Column(JSONB, nullable=False)
    description = Column(String, nullable=False)
    start_time = Column(String, nullable=False)
    end_time = Column(String, nullable=False)
    # creator_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    created_at = Column(String, default=datetime.now(timezone.utc).isoformat())

    # creator = relationship("User", back_populates="calendar_events")

    # @validates("creator_id")
    # def validate_creator(self, key, value):
    #     user = SessionLocal.query(User).filter_by(id=value).first()
    #     if user and user.role == RoleType.STUDENT:
    #         raise ValueError("Students cannot create calendar events.")
    #     return value

class UserCalendarEvent(Base):
    __tablename__ = "user_calendar_events"
    id = Column(Integer, primary_key=True)
    events = Column(JSONB, nullable=False)
    description = Column(String, nullable=False)
    start_time = Column(String, nullable=False)
    end_time = Column(String, nullable=False)
    creator_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
    created_at = Column(String, default=datetime.now(timezone.utc).isoformat())

    creator = relationship("User", back_populates="calendar_events")

    @validates("creator_id")
    def validate_creator(self, key, value):
        user = SessionLocal.query(User).filter_by(id=value).first()
        if user and user.role == RoleType.STUDENT:
            raise ValueError("Students cannot create calendar events.")
        return value

class TeamCalendarEvent(Base):
    __tablename__ = "team_calendar_events"
    id = Column(Integer, primary_key=True)
    events = Column(JSONB, nullable=False)
    description = Column(String, nullable=False)
    start_time = Column(String, nullable=False)
    end_time = Column(String, nullable=False)
    creator_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(String, default=datetime.now(timezone.utc).isoformat())

    creator = relationship("User", back_populates="team_calendar_events")

    @validates("creator_id")
    def validate_creator(self, key, value):
        user = SessionLocal.query(User).filter_by(id=value).first()
        if user and user.role == RoleType.STUDENT:
            raise ValueError("Students cannot create calendar events.")
        return value
    
class Team_TA(Base):
    __tablename__ = "team_tas"
    id = Column(Integer, primary_key=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    ta_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    team = relationship("Team", backref="team_tas")
    ta = relationship("User", backref="ta_teams")

class Channel(Base):
    __tablename__ = "channels"
    id = Column(Integer, primary_key=True)
    name = Column(String(50), nullable=False)
    type = Column(String(10), nullable=False)  # global, team, or ta-team
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=True)
    messages = relationship("Message", back_populates="channel")

class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True)
    content = Column(Text, nullable=False)
    sender_id = Column(Integer, ForeignKey("users.id"))
    channel_id = Column(Integer, ForeignKey("channels.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    message_type = Column(String(10), default='text')
    file_name = Column(String(255))

    sender = relationship("User", back_populates="messages")
    channel = relationship("Channel", back_populates="messages")

class TeamSkill(Base):
    __tablename__ = "team_skills"

class UserSkill(Base):
    __tablename__ = "user_skills"


# Define OTP database table
class UserOTP(Base):
    __tablename__ = "user_otps"
    
    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    hashed_otp = Column(String, nullable=False)
    expires_at = Column(String, nullable=False)  # ISO 8601 format
    
    # Relationship with User
    user = relationship("User", backref="otp_record")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Database assisting functions



## Calendar functions - get
def get_global_events(db:Session):
    top_row = db.query(GlobalCalendarEvent).first()
    if (top_row):
        return top_row.events
    return None

def get_personal_events(user: User, db: Session):
    row = db.query(UserCalendarEvent).filter_by(creator_id=user.id).first()
    if row:
        _events = row.events
        for event in _events:
            event["type"] = "personal"
        return row.events
    return None 

def get_team_events(user: User, db: Session):
    # if(user.role == RoleType.STUDENT):
    assert(user.role == RoleType.STUDENT)
    teams = user.teams
    team_events = []
    for team in teams:
        row = db.query(TeamCalendarEvent).filter_by(creator_id=team.id).first()
        if row:
            _events = row.events
            for event in _events:
                event["type"] = "team"
            team_events += _events
    return team_events

def get_events(user: User, db: Session):
    '''
    Get all events for a user

    Assumes that global events, team events
    and personal events are all lists
    '''
    global_events = get_global_events(db)
    team_events = get_team_events(user, db)
    personal_events = get_personal_events(user, db)
    return global_events + team_events + personal_events


def split_events(events):
    global_events = []
    personal_events = []
    team_events = []
    for event in events:
        if "type" not in event:
            continue
        if event["type"] == "global":
            global_events.append(event)
        elif event["type"] == "personal":
            personal_events.append(event)
        elif event["type"] == "team":
            team_events.append(event)
        else:
            continue # throw it
    return global_events, personal_events, team_events

## Calendar functions - overwriting
def overwrite_global_events(events, db: Session):
    '''
    Overwrite the global events with the new events
    '''
    top_row = db.query(GlobalCalendarEvent).first()
    if top_row:
        print(events)
        top_row.events = events
    else:
        top_row = GlobalCalendarEvent(events=events)
        db.add(top_row)
    db.commit()
    db.refresh(top_row)

def overwrite_personal_events(user: User, events, db: Session):
    '''
    Overwrite the personal events with the new events
    '''
    row = db.query(UserCalendarEvent).filter_by(creator_id=user.id).first()
    if row:
        row.events = events
    else:
        row = UserCalendarEvent(events=events, creator_id=user.id)
        db.add(row)
    db.commit()
    db.refresh(row)

def overwrite_team_events(user: User, events, db: Session):
    '''
    Overwrite the team events with the new events
    '''
    teams = user.teams
    for team in teams:
        row = db.query(TeamCalendarEvent).filter_by(creator_id=team.id).first()
        if row:
            row.events = events
        else:
            row = TeamCalendarEvent(events=events, creator_id=team.id)
            db.add(row)
    db.commit()
    db.refresh(row)


class QueryBaseModel(BaseModel):
    token: str = Header(None)

class UserBase(BaseModel):
    name: str
    email: EmailStr
    role: RoleType

# Additional Pydantic models for authentication
class LoginRequest(BaseModel):
    username: str
    password: str

class ResetPasswordRequest(BaseModel):
    new_password: str
    confirm_password: str

class CreateProfRequest(BaseModel):
    name: str
    email: EmailStr

class TempRegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str
    confirm_password: str
    role: RoleType

class SkillRequest(BaseModel):
    name: str
    bgColor: str
    fgColor: str
    icon: str

# Form-related Pydantic models
class FormCreateRequest(BaseModel):
    title: str
    # description: Optional[str] = None
    form_json: Dict[str, Any]
    deadline: str
    # target_type: RoleType
    # target_id: int
    
    @validator('deadline')
    def validate_deadline(cls, v):
        try:
            # Validate ISO 8601 format
            datetime.fromisoformat(v.replace('Z', '+00:00'))
            return v
        except ValueError:
            raise ValueError("Invalid deadline format. Use ISO 8601 (YYYY-MM-DDTHH:MM:SSZ)")

class FormResponseSubmit(BaseModel):
    form_id: int
    user_id: int
    response_data: str  # JSON serialized response data

class UserIdRequest(BaseModel):
    user_id: int

# Skill-related Pydantic models
class SkillBase(BaseModel):
    name: str
    bgColor: str
    color: str
    icon: str

class SkillCreate(SkillBase):
    pass

class SkillResponse(SkillBase):
    id: int

    class Config:
        orm_mode = True

class AssignSkillsRequest(BaseModel):
    user_id: int
    skill_ids: List[int]

class AssignTeamSkillsRequest(BaseModel):
    team_id: int
    skill_ids: List[int]

class GradeableCreateRequest(BaseModel):
    title: str
    #description: str
    #due_date: str  # ISO 8601 format
    max_points: int
    
    @validator('due_date')
    def validate_due_date(cls, v):
        try:
            # Validate ISO 8601 format
            datetime.fromisoformat(v.replace('Z', '+00:00'))
            return v
        except ValueError:
            raise ValueError("Invalid due date format. Use ISO 8601 (YYYY-MM-DDTHH:MM:SSZ)")
            
    @validator('max_points')
    def validate_max_points(cls, v):
        if v <= 0:
            raise ValueError("Maximum points must be greater than zero")
        return v

app = FastAPI()

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

print("Creating tables...")
Base.metadata.create_all(bind=engine)
print("Tables created!")

# Add missing columns to submittables table if they don't exist
with engine.connect() as connection:
    connection.execute(text("""
        DO $$ 
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name = 'submittables' AND column_name = 'file_url') THEN
                ALTER TABLE submittables ADD COLUMN file_url VARCHAR;
            END IF;
            
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name = 'submittables' AND column_name = 'original_filename') THEN
                ALTER TABLE submittables ADD COLUMN original_filename VARCHAR;
            END IF;

            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name = 'submittables' AND column_name = 'max_score') THEN
                ALTER TABLE submittables ADD COLUMN max_score INTEGER NOT NULL DEFAULT 100;
            END IF;
        END $$;
    """))
    connection.commit()

    # Add missing columns to submissions table if they don't exist
    connection.execute(text("""
        DO $$ 
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name = 'submissions' AND column_name = 'score') THEN
                ALTER TABLE submissions ADD COLUMN score INTEGER;
            END IF;
        END $$;
    """))
    connection.commit()

# Create default roles if they don't exist
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

###
# Authentication
###

SECRET_KEY = "a3eca18b09973b1890cfbc94d5322c1aae378b73ea5eee0194ced065175d04aa"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Database dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Authentication utilities
def create_hashed_password(password: str):
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def generate_token(data: dict, expires_delta: timedelta):
    to_encode = data.copy()
    expire = datetime.utcnow() + expires_delta
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def generate_random_string(length=8):
    return "hello123"
    # return "".join(random.choices(string.ascii_letters + string.digits, k=length))

def resolve_token(token: str = Header(None)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload["sub"]
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

def check_user_permitted(user_id: int, role: RoleType):
    user = SessionLocal.query(User).filter_by(id=user_id).first()
    if user.role.role != role:
        raise HTTPException(status_code=403, detail="User does not have permission to access this resource")

# Authentication dependencies
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")

def get_verified_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
        return {"username": username}
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired")
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


def get_current_user_from_string(token: str, db: Session):
    print("In here")
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception
    
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise credentials_exception
    
    role = db.query(Role).filter(Role.id == user.role_id).first().role
    
    return {"user": user, "role": role}

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception
    
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise credentials_exception
    
    role = db.query(Role).filter(Role.id == user.role_id).first().role
    
    return {"user": user, "role": role}

def prof_required(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if not username:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
            
        # Check if user is a professor
        user = db.query(User).filter(User.username == username).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User not found")
            
        role = db.query(Role).filter(Role.id == user.role_id).first()
        if role.role != RoleType.PROF:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized, professor access required")
            
        return payload
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

def prof_or_ta_required(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if not username:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
            
        # Check if user exists
        user = db.query(User).filter(User.username == username).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User not found")
            
        # Check if user is a professor or TA
        role = db.query(Role).filter(Role.id == user.role_id).first()
        if role.role not in [RoleType.PROF, RoleType.TA]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, 
                detail="Not authorized, professor or TA access required"
            )
            
        return payload
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

# Initialize default data
create_default_roles()
create_default_admin()

# Authentication endpoints
@app.post("/login")
def login(request: Annotated[OAuth2PasswordRequestForm, Depends()], db: Session = Depends(get_db)):
    try:
        user = db.query(User).filter(User.username == request.username).first()
        
        # Verify credentials
        if not user or not verify_password(request.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, 
                detail="Invalid username or password"
            )

        # Get the role
        role = db.query(Role).filter(Role.id == user.role_id).first()
        if not role:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                detail="User role not found"
            )
        
        # Generate token
        token = generate_token(
            {"sub": user.username}, 
            timedelta(days=1)
        )
        
        return {
            "access_token": token,
            "token_type": "bearer",
            "role": role.role.value
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"Login error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@app.post("/reset-password")
def reset_password(
    request: ResetPasswordRequest,
    current_user_data: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Check if passwords match
    if request.new_password != request.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Passwords don't match"
        )
    
    # Get user object
    user = current_user_data["user"]
    
    # Hash the new password
    hashed_password = create_hashed_password(request.new_password)
    
    # Update password
    user.hashed_password = hashed_password
    db.commit()
    
    return {"message": "Password reset successfully"}

@app.post("/create-prof")
def create_prof(
    request: CreateProfRequest,
    token: str = Depends(prof_required),
    db: Session = Depends(get_db)
):
    # Extract username from email
    username = request.email.split('@')[0]
    
    # Check if username already exists
    existing_user = db.query(User).filter(User.username == username).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=f"Username {username} already exists"
        )
    
    # Get prof role id
    prof_role = db.query(Role).filter(Role.role == RoleType.PROF).first()
    if not prof_role:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Professor role not found"
        )
    
    # Generate temporary password
    temporary_password = generate_random_string(10)
    hashed_password = create_hashed_password(temporary_password)
    
    # Create new professor
    new_prof = User(
        name=request.name, 
        email=request.email, 
        username=username, 
        hashed_password=hashed_password,
        role_id=prof_role.id
    )
    
    db.add(new_prof)
    db.commit()
    db.refresh(new_prof)
    
    return {
        "message": "Professor created successfully",
        "username": username,
        "temporary_password": temporary_password
    }

"""
CSV File Format for Student Upload:
Expected columns:
- Name: Full name of the student (e.g., "John Doe")
- Email: Valid email address (e.g., "john.doe@example.com")
- Username: Unique username for login (e.g., "jdoe" or "john.doe")

Example CSV format:
```
Name,Email,Username
John Doe,john.doe@example.com,jdoe
Jane Smith,jane.smith@example.com,jsmith
```

Notes:
- The first row must contain the column headers as shown above
- All three columns are required for each student
- Usernames must be unique across all users in the system
- Each row will create a new student account with a randomly generated temporary password
"""
@app.post("/upload-students")
async def upload_students(
    file: UploadFile = File(...),
    token: str = Depends(prof_or_ta_required),  # Updated dependency
    db: Session = Depends(get_db)
):
    # Ensure the file is a CSV
    if not file.filename.endswith('.csv'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only CSV files are allowed"
        )
    
    try:
        # Read file content
        content = await file.read()
        content_str = content.decode('utf-16')
        
        try:
            students = extract_student_data_from_content(content_str)
        except CSVFormatError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"CSV format error: {str(e)}"
            )
        
        created_students = []
        errors = []
        
        # Get student role
        student_role = db.query(Role).filter(Role.role == RoleType.STUDENT).first()
        if not student_role:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Student role not found"
            )
        
        # Process each student
        for student in students:
            try:
                username = student['Username']
                
                # Check if username already exists
                existing_user = db.query(User).filter(User.username == username).first()
                if existing_user:
                    errors.append(f"Username {username} already exists")
                    continue
                
                # Generate random password
                temp_password = generate_random_string(10)
                hashed_password = create_hashed_password(temp_password)
                
                # Create new student
                new_student = User(
                    name=student['Name'],
                    email=student['Email'],
                    username=username,
                    hashed_password=hashed_password,
                    role_id=student_role.id
                )
                
                # Add and commit
                db.add(new_student)
                db.commit()
                db.refresh(new_student)
                
                # Add to successful creations
                created_students.append({
                    "name": new_student.name,
                    "email": new_student.email,
                    "username": username,
                    "temp_password": temp_password
                })
                
            except Exception as e:
                errors.append(f"Error processing student {student}: {str(e)}")
        
        return {
            "message": f"Processed {len(created_students)} students",
            "created_students": created_students,
            "errors": errors
        }
    
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing CSV file: {str(e)}"
        )

@app.post("/upload-tas")
async def upload_tas(
    file: UploadFile = File(...),
    token: str = Depends(prof_required),
    db: Session = Depends(get_db)
):
    # Ensure the file is a CSV
    if not file.filename.endswith('.csv'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only CSV files are allowed"
        )
    
    try:
        # Read file content
        content = await file.read()
        content_str = content.decode('utf-8')
        
        try:
            tas = extract_ta_data_from_content(content_str)
        except CSVFormatError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"CSV format error: {str(e)}"
            )
            
        created_tas = []
        errors = []
        
        # Get TA role
        ta_role = db.query(Role).filter(Role.role == RoleType.TA).first()
        if not ta_role:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="TA role not found"
            )
        
        # Process each TA
        for ta in tas:
            try:
                username = ta['Username']
                
                # Check if username already exists
                existing_user = db.query(User).filter(User.username == username).first()
                if existing_user:
                    errors.append(f"Username {username} already exists")
                    continue
                
                # Generate random password
                temp_password = generate_random_string(10)
                hashed_password = create_hashed_password(temp_password)
                
                # Create new TA
                new_ta = User(
                    name=ta['Name'],
                    email=ta['Email'],
                    username=username,
                    hashed_password=hashed_password,
                    role_id=ta_role.id
                )
                
                # Add and commit
                db.add(new_ta)
                db.commit()
                db.refresh(new_ta)
                
                # Add to successful creations
                created_tas.append({
                    "name": new_ta.name,
                    "email": new_ta.email,
                    "username": username,
                    "temp_password": temp_password
                })
                
            except Exception as e:
                errors.append(f"Error processing TA {ta}: {str(e)}")
        
        return {
            "message": f"Processed {len(created_tas)} TAs",
            "created_tas": created_tas,
            "errors": errors
        }
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing CSV file: {str(e)}"
        )

@app.post("/register-temp")
def register_temp(
    request: TempRegisterRequest,
    db: Session = Depends(get_db)
):
    # Check if passwords match
    if request.password != request.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Passwords don't match"
        )
    
    # Generate username from email
    username = request.email.split('@')[0]
    
    # Check if username already exists
    existing_user = db.query(User).filter(User.username == username).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Username {username} already exists"
        ) 
    
    # Check if email already exists
    existing_email = db.query(User).filter(User.email == request.email).first()
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Email {request.email} is already registered"
        )
    
    # Get role ID
    role = db.query(Role).filter(Role.role == request.role).first()
    if not role:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Role {request.role} does not exist"
        )
    
    # Hash the password
    hashed_password = create_hashed_password(request.password)
    
    # Create new user
    new_user = User(
        name=request.name,
        email=request.email,
        username=username,
        hashed_password=hashed_password,
        role_id=role.id
    )
    
    # Add user to database
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    return {
        "message": f"User registered successfully as {request.role}",
        "username": username
    }

@app.get("/dashboard/gradeables") # TODO: 
def get_gradeables():
    pass

app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

class Announcements(BaseModel):
    title: str
    description: dict
    #file_patch: str

class Show(BaseModel):
    id: int
    creator_id: int
    created_at: str
    title: str
    content: str  # Contains Markdown formatted text
    url_name: Optional[str] = None

    class Config:
        orm_mode = True

@app.post('/announcements', status_code=status.HTTP_201_CREATED)
async def create(
    title: str = FastAPIForm(...),
    description: str = FastAPIForm(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    try:
        # Create file path
        file_extension = os.path.splitext(file.filename)[1]
        file_name = f"{uuid.uuid4()}{file_extension}"
        file_path = os.path.join("uploads", file_name)
        
        # Ensure uploads directory exists
        os.makedirs("uploads", exist_ok=True)
        
        # Save the file
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        
        # Create announcement in database
        db_announcement = Announcement(
            title=title,
            content=description,
            url_name=file_name,
            creator_id=1  # Default creator ID
        )
        
        db.add(new_announcement)
        db.commit()
        db.refresh(new_announcement)
        
        return new_announcement
        
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get('/announcements/{announcement_id}/download')
async def download_announcement_file(
    announcement_id: int,
    db: Session = Depends(get_db)
):
    try:
        announcement = db.query(Announcement).filter(Announcement.id == announcement_id).first()
        if not announcement or not announcement.url_name:
            raise HTTPException(status_code=404, detail="File not found")
        
        file_path = os.path.join("uploads", announcement.url_name)
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="File not found")
        
        # Determine content type based on file extension
        file_extension = os.path.splitext(announcement.url_name)[1].lower()
        content_type = {
            '.pdf': 'application/pdf',
            '.doc': 'application/msword',
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.txt': 'text/plain'
        }.get(file_extension, 'application/octet-stream')
        
        return FileResponse(
            file_path,
            filename=announcement.url_name,
            media_type=content_type,
            headers={
                "Content-Disposition": f'attachment; filename="{announcement.url_name}"'
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get('/announcements', response_model=List[Show])
def all(db: Session = Depends(get_db)):
    announcements = db.query(Announcement).order_by(Announcement.created_at.desc()).all()
    return announcements

@app.delete('/announcements/{announcement_id}')
def destroy(announcement_id: int, db: Session = Depends(get_db)):
    announcement = db.query(Announcement).filter(Announcement.id == announcement_id).first()
    if not announcement:
        raise HTTPException(status_code=404, detail="Announcement not found")
    
    try:
        # Delete the associated file if it exists
        if announcement.url_name:
            file_path = os.path.join("uploads", announcement.url_name)
            if os.path.exists(file_path):
                os.remove(file_path)
        
        # Delete the announcement from database
        db.delete(announcement)
        db.commit()
        return {"message": "Announcement deleted successfully"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error deleting announcement: {str(e)}")

@app.put('/announcements/{id}', status_code=status.HTTP_202_ACCEPTED)
def update(
    id: int,
    title: Annotated[str, Form()],
    description: Annotated[str, Form()],  # Now expects plain text
    file: UploadFile | None = None,
    db: Session = Depends(get_db)
):
    announcement = db.query(Announcement).filter(Announcement.id==id)
    if not announcement.first():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f'Announcement with id: {id} not found')
    
    new_url_name = announcement.first().url_name
    if file:
        if announcement.first().url_name and os.path.exists(announcement.first().url_name):
            os.remove(announcement.first().url_name)
        
        file_extension = file.filename.split('.')[-1]
        file_name = f"{uuid.uuid4()}.{file_extension}"
        new_url_name = f"uploads/{file_name}"
        with open(new_url_name, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    
    # Update only the modifiable fields
    announcement.first().title = title
    announcement.first().content = description  # Store description directly as string
    announcement.first().url_name = new_url_name

    db.commit()
    db.refresh(announcement.first())
    return {"detail": "Announcement updated", "announcement": announcement.first()}

@app.delete('/announcements/{id}', status_code=status.HTTP_204_NO_CONTENT)
def destroy(id:int, db:Session=Depends(get_db)):
    blog=db.query(Announcement).filter(Announcement.id==id)
    if not blog.first():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f'Announcement with id: {id} not found')
    if blog.first().url_name and os.path.exists(blog.first().url_name):  # Changed from file_path to url_name
        os.remove(blog.first().url_name)
    blog.delete(synchronize_session=False)
    db.commit()
    return 'done'


@app.get('/announcements', response_model=List[Show])
def all(db:Session = Depends(get_db)):
    blogs = db.query(Announcement).all()
    return blogs

@app.get('/announcements/{id}', status_code=200, response_model=Show)
def show(id, response: Response, db:Session=Depends(get_db)):
    blog = db.query(Announcement).filter(Announcement.id==id).first()
    if not blog:
        response.status_code=status.HTTP_404_NOT_FOUND
        return {'details': f'blog with {id} not found'}
    return blog

@app.post("/quiz/create")
def create_quiz():
    pass

@app.get("/forms/")
def get_forms():
    pass

@app.post("/forms/create")
def create_form():
    pass

class TABase(BaseModel):
    name: str
    skills: List[str]

class TeamBase(BaseModel):
    team_name: str
    skills: List[str]

class TADisplay(TABase):
    id: int
    class Config:
        orm_mode = True

class TeamDisplay(TeamBase):
    id: int
    class Config:
        orm_mode = True

class AllocationResponse(BaseModel):
    team_id: int
    required_skill_ids: List[int]
    assigned_ta_ids: List[int]


def get_allocation(n: int, db: Session):
    # Get all teams and their skills
    teams = db.query(Team).all()
    allocations = []
    
    for team in teams:
        # Get team's required skills
        team_skills = db.query(TeamSkill.skill_id).filter(
            TeamSkill.team_id == team.id
        ).all()
        team_skill_ids = [skill[0] for skill in team_skills]
        
        # Find TAs with matching skills
        tas = db.query(User).join(
            UserSkill,
            User.id == UserSkill.user_id
        ).filter(
            UserSkill.skill_id.in_(team_skill_ids),
            User.role_id == 2  # Assuming role_id 2 is for TAs
        ).distinct().limit(n).all()
        
        allocation = {
            "team_id": team.id,
            "assigned_ta_ids": [ta.id for ta in tas]
        }
        allocations.append(allocation)
    
    return allocations

@app.get("/match/{n}", response_model=dict)
async def create_match(n: int, db: Session = Depends(get_db)):
    if n <= 0:
        raise HTTPException(status_code=400, detail="Number of TAs per team must be positive")
    
    try:
        # Get allocations using matching algorithm
        allocations = get_allocation(n, db)
        
        # Clear existing team_tas entries
        db.query(Team_TA).delete()
        
        # Insert new allocations
        for allocation in allocations:
            team_id = allocation["team_id"]
            for ta_id in allocation["assigned_ta_ids"]:
                new_team_ta = Team_TA(
                    team_id=team_id,
                    ta_id=ta_id
                )
                db.add(new_team_ta)
        
        db.commit()
        return {"message": "allocation is done"}
    
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/match", response_model=dict)
async def get_match(db: Session = Depends(get_db)):
    try:
        results = db.execute(text("""
            SELECT 
                t.id as team_id,
                t.name as team_name,
                u.id as ta_id,
                u.name as ta_name
            FROM teams t
            JOIN team_tas tt ON t.id = tt.team_id
            JOIN users u ON tt.ta_id = u.id
            ORDER BY t.id, u.id
        """)).fetchall()
        
        teams_dict = {}
        for row in results:
            team_id = row[0]
            if team_id not in teams_dict:
                teams_dict[team_id] = {
                    "team_id": team_id,
                    "team_name": row[1],
                    "tas": []
                }
            teams_dict[team_id]["tas"].append({
                "ta_id": row[2],
                "ta_name": row[3]
            })
        
        return {"teams": list(teams_dict.values())}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Calendar

class CalendarUpdateModel(BaseModel):
    events: List[Any]
    # token: str = Header(None)

@app.post("/calendar/update")
def update_calendar(
    calendar_update_model: CalendarUpdateModel,
    db: Session = Depends(get_db),
    # user_id: int = Depends(resolve_token)
):
    # user = db.query(User).filter_by(id=user_id).first()
    print(calendar_update_model.events)
    global_events = calendar_update_model.events
    # global_events, personal_events, team_events = split_events(calendar_update_model.events)
    print(global_events)
    overwrite_global_events(global_events, db)
    return {"message": "Calendar updated"}
    # if user.role == RoleType.PROF:
    #     overwrite_global_events(events, db)
    # elif user.role == RoleType.STUDENT:
    #     overwrite_personal_events(user, events, db)
    # elif user.role == RoleType.TA:
    #     overwrite_team_events(user, events, db)
    # return {"message": "Calendar updated"}
    # if the role is admin
    # select all the global events

    # overwrite_global_events



    
    pass

@app.get("/calendar/")
def get_calendar(
    db: Session = Depends(get_db),
    # user_id: int = Depends(resolve_token)
):
    # Get the global events
    global_events = get_global_events(db)
    print(global_events)
    return JSONResponse(status_code=201, content=global_events)
    # return {"message": "Calendar retrieved", "events": global_events}



@app.get("/people/")
def get_people(db: Session = Depends(get_db)):
    users = db.query(User).all()
    return_data = []
    role_id_to_role = { 1 : "Professor", 2 : "Student", 3 : "TA"}
    for user in users:
        user_data = {}
        user_data["id"] = user.id
        user_data["name"] = user.name
        user_data["email"] = user.email
        user_data["role"] = role_id_to_role[user.role_id]
        return_data.append(user_data)
    return return_data
    # return {"access_token": token, "token_type": "bearer", "role": role}


@app.get("/team/")
def get_team(db: Session = Depends(get_db)):
    users = db.query(Team).all()
    return_data = []
    #role_id_to_role = { 1 : "Professor", 2 : "Student", 3 : "TA"}
    for user in users:
        user_data = {}
        user_data["id"] = user.id
        user_data["name"] = user.name
        user_data["details"] = user.members
        return_data.append(user_data)
    return return_data


# Form-related helper functions
def create_form_db(form_data: FormCreateRequest, db: Session) -> Dict[str, Any]:
    """
    Create a new form in the database
    
    Parameters:
    - form_data: FormCreateRequest object
    - db: Database session
    
    Returns:
    - Dictionary with form details including the generated ID
    """
    try:
        # Create form object
        new_form = Form(
            title=form_data.title,
            # description=form_data.description,
            description = "Form description",
            # target_type=form_data.target_type,
            # target_id=form_data.target_id,
            # target_type= RoleType.STUDENT,
            created_at=datetime.now(timezone.utc).isoformat(),
            form_json=json.dumps(form_data.form_json),
            deadline=form_data.deadline
        )
        
        # Add to database
        db.add(new_form)
        db.commit()
        db.refresh(new_form)
        
        return {
            "id": new_form.id,
            "title": new_form.title,
            "created_at": new_form.created_at,
            "deadline": form_data.deadline
        }
    except Exception as e:
        db.rollback()
        print(f"error creating form: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error creating form: {str(e)}")

def store_form_response_db(response_data: FormResponseSubmit, db: Session) -> Dict[str, Any]:
    """
    Store a user's response to a form
    
    Parameters:
    - response_data: FormResponseSubmit object
    - db: Database session
    
    Returns:
    - Dictionary with operation result
    """
    try:
        # Check if form exists
        form = db.query(Form).filter(Form.id == response_data.form_id).first()
        
        if not form:
            raise HTTPException(status_code=404, detail="Form not found")
        
        # Check deadline
        if is_deadline_passed(form.deadline):
            raise HTTPException(status_code=400, detail="Form submission deadline has passed")
        
        # Check if user has already responded
        existing_response = db.query(FormResponse).filter(
            FormResponse.form_id == response_data.form_id,
            FormResponse.user_id == response_data.user_id
        ).first()
        
        if existing_response:
            # Update existing response
            existing_response.response_data = response_data.response_data
            existing_response.submitted_at = datetime.now(timezone.utc).isoformat()
            message = "Response updated successfully"
        else:
            # Add new response
            new_response = FormResponse(
                form_id=response_data.form_id,
                user_id=response_data.user_id,
                response_data=response_data.response_data,
                submitted_at=datetime.now(timezone.utc).isoformat()
            )
            db.add(new_response)
            message = "Response submitted successfully"
        
        db.commit()
        
        return {
            "message": message,
            "form_id": response_data.form_id,
            "user_id": response_data.user_id
        }
    except HTTPException as he:
        db.rollback()
        raise he
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error storing form response: {str(e)}")

def get_form_by_id_db(form_id: int, db: Session) -> Dict[str, Any]:
    """
    Retrieve a form by its ID
    
    Parameters:
    - form_id: The ID of the form to retrieve
    - db: Database session
    
    Returns:
    - Dictionary with form details
    """
    try:
        form = db.query(Form).filter(Form.id == form_id).first()
        if not form:
            raise HTTPException(status_code=404, detail="Form not found")
        
        # Return form data
        return {
            "id": form.id,
            "title": form.title,
            "description": form.description,
            "created_at": form.created_at,
            "deadline": form.deadline,
            "form_json": json.loads(form.form_json) if hasattr(form, "form_json") else None,
            "target_type": form.target_type.value,
            "target_id": form.target_id
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving form: {str(e)}")

def get_user_response_db(form_id: int, user_id: int, db: Session) -> Dict[str, Any]:
    """
    Get a specific user's response to a form
    
    Parameters:
    - form_id: ID of the form
    - user_id: ID of the user
    - db: Database session
    
    Returns:
    - Dictionary with user's response data or None if not found
    """
    try:
        form = db.query(Form).filter(Form.id == form_id).first()
        if not form:
            raise HTTPException(status_code=404, detail="Form not found")
        
        user_response = db.query(FormResponse).filter(
            FormResponse.form_id == form_id,
            FormResponse.user_id == user_id
        ).first()
        
        return {
            "found": user_response is not None,
            "form_id": form_id,
            "user_id": user_id,
            "response_data": json.loads(user_response.response_data) if user_response else None,
            "submitted_at": user_response.submitted_at if user_response else None
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving user response: {str(e)}")

def is_deadline_passed(deadline: str) -> bool:
    """
    Check if a form's deadline has passed
    
    Parameters:
    - deadline: ISO 8601 formatted deadline string
    
    Returns:
    - True if deadline has passed, False otherwise
    """
    try:
        # Parse deadline into datetime object
        deadline_dt = datetime.fromisoformat(deadline.replace('Z', '+00:00'))
        # Compare with current time
        return datetime.now(deadline_dt.tzinfo) > deadline_dt
    except Exception as e:
        # If there's any error parsing, default to assuming deadline has passed
        raise ValueError(f"Invalid deadline format: {str(e)}")

def get_all_forms_db(user_id: Optional[int] = None, db: Session = None) -> List[Dict[str, Any]]:
    """
    Get all forms in the database
    
    Parameters:
    - user_id: Optional user ID to check if the user has submitted the form
    - db: Database session
    
    Returns:
    - List of form documents with data relevant for listing
    """
    try:
        # Get all forms
        forms = db.query(Form).all()
        result = []
        
        for form in forms:
            form_data = {
                "id": form.id,
                "title": form.title,
                "description": form.description,
                "created_at": form.created_at,
                "deadline": form.deadline,
                # "target_type": form.target_type.value,
                # "target_id": form.target_id,
                "score": "-/-",  # Placeholder for score
                "deadline_passed": is_deadline_passed(form.deadline)
            }
            
            if user_id:
                # Check if user has submitted a response
                response = db.query(FormResponse).filter(
                    FormResponse.form_id == form.id,
                    FormResponse.user_id == user_id
                ).first()
                form_data["attempt"] = response is None
            else:
                form_data["attempt"] = False
            
            result.append(form_data)
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving forms: {str(e)}")

# Form-related endpoints
@app.post("/api/forms/create")
async def api_create_form(form_data: FormCreateRequest, db: Session = Depends(get_db)):
    """Create a new form"""
    result = create_form_db(form_data, db)
    return JSONResponse(status_code=201, content=result)

@app.post("/api/forms/submit")
async def api_submit_response(form_response: FormResponseSubmit, db: Session = Depends(get_db)):
    """Submit a response to a form"""
    result = store_form_response_db(form_response, db)
    return JSONResponse(status_code=201, content=result)

@app.get("/api/forms/{form_id}")
async def api_get_form(form_id: int, db: Session = Depends(get_db)):
    """Get a form by ID"""
    form = get_form_by_id_db(form_id, db)
    return JSONResponse(status_code=200, content=form["form_json"])

@app.get("/api/forms/{form_id}/check-deadline")
async def api_check_deadline(form_id: int, db: Session = Depends(get_db)):
    """Check if a form's deadline has passed"""
    form = get_form_by_id_db(form_id, db)
    deadline_passed = is_deadline_passed(form.get("deadline", ""))
    return JSONResponse(
        status_code=200, 
        content={
            "form_id": form_id,
            "form_name": form.get("title", ""),
            "deadline": form.get("deadline", ""),
            "deadline_passed": deadline_passed
        }
    )

@app.post("/api/get_forms")
async def api_get_forms(user: UserIdRequest, db: Session = Depends(get_db)):
    """Get all forms with info about whether the user has submitted a response"""
    forms = get_all_forms_db(user.user_id, db)
    return JSONResponse(status_code=200, content=forms)

@app.get("/api/forms/{form_id}/user/{user_id}")
async def api_get_user_response(form_id: int, user_id: int, db: Session = Depends(get_db)):
    """Get a user's response to a form"""
    response = get_user_response_db(form_id, user_id, db)
    return JSONResponse(status_code=200, content=response)

@app.get("/api/skills/")
async def get_all_skills(db: Session = Depends(get_db)):
    """Get all skills from the database"""
    skills = db.query(Skill).all()
    results = []
    for skill in skills:
        results.append({
            "id": skill.id,
            "name": skill.name,
            "bgColor": skill.bgColor,
            "color": skill.color,
            "icon": skill.icon
        })
    return JSONResponse(status_code=200, content=results)

@app.post("/api/skills/create")
async def create_skill(skill: SkillCreate, db: Session = Depends(get_db), token: str = Depends(prof_or_ta_required)):
    """Create a new skill"""
    try:
        # Check if skill with same name already exists
        existing = db.query(Skill).filter(Skill.name == skill.name).first()
        if existing:
            raise HTTPException(status_code=400, detail=f"Skill with name '{skill.name}' already exists")
        
        # Create new skill
        new_skill = Skill(
            name=skill.name,
            bgColor=skill.bgColor,
            color=skill.color,
            icon=skill.icon
        )
        
        db.add(new_skill)
        db.commit()
        db.refresh(new_skill)
        
        return JSONResponse(status_code=201, content={
            "id": new_skill.id,
            "name": new_skill.name,
            "bgColor": new_skill.bgColor,
            "color": new_skill.color,
            "icon": new_skill.icon
        })
    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error creating skill: {str(e)}")

@app.get("/api/users/{user_id}/skills")
async def get_user_skills(user_id: int, db: Session = Depends(get_db)):
    """Get all skills for a specific user (TA)"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Check if user is a TA
    role = db.query(Role).filter(Role.id == user.role_id).first()
    if role.role != RoleType.TA:
        raise HTTPException(status_code=400, detail="Skills can only be assigned to TAs")
    
    skills = user.skills
    results = []
    for skill in skills:
        results.append({
            "id": skill.id,
            "name": skill.name,
            "bgColor": skill.bgColor,
            "color": skill.color,
            "icon": skill.icon
        })
    
    return JSONResponse(status_code=200, content=results)

@app.post("/api/users/assign-skills")
async def assign_skills_to_user(request: AssignSkillsRequest, db: Session = Depends(get_db), token: str = Depends(prof_or_ta_required)):
    """Assign skills to a user (TA)"""
    try:
        user = db.query(User).filter(User.id == request.user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Check if user is a TA
        role = db.query(Role).filter(Role.id == user.role_id).first()
        if role.role != RoleType.TA:
            raise HTTPException(status_code=400, detail="Skills can only be assigned to TAs")
        
        # Get all skills by IDs
        skills = db.query(Skill).filter(Skill.id.in_(request.skill_ids)).all()
        if len(skills) != len(request.skill_ids):
            raise HTTPException(status_code=400, detail="Some skill IDs are invalid")
        
        # Clear existing skills and assign new ones
        user.skills = skills
        db.commit()
        
        return JSONResponse(status_code=200, content={
            "message": "Skills assigned successfully",
            "user_id": user.id,
            "skill_count": len(skills)
        })
    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error assigning skills: {str(e)}")

@app.delete("/api/skills/{skill_id}")
async def delete_skill(skill_id: int, db: Session = Depends(get_db), token: str = Depends(prof_required)):
    """Delete a skill (professors only)"""
    try:
        skill = db.query(Skill).filter(Skill.id == skill_id).first()
        if not skill:
            raise HTTPException(status_code=404, detail="Skill not found")
        
        # Remove the skill from all users that have it
        for user in skill.users:
            user.skills.remove(skill)
        
        # Delete the skill
        db.delete(skill)
        db.commit()
        
        return JSONResponse(status_code=200, content={
            "message": "Skill deleted successfully",
            "id": skill_id
        })
    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error deleting skill: {str(e)}")

@app.get("/api/teams/{team_id}/skills")
async def get_team_skills(team_id: int, db: Session = Depends(get_db)):
    """Get all skills for a specific team"""
    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    
    skills = team.skills
    results = []
    for skill in skills:
        results.append({
            "id": skill.id,
            "name": skill.name,
            "bgColor": skill.bgColor,
            "color": skill.color,
            "icon": skill.icon
        })
    
    return JSONResponse(status_code=200, content=results)

@app.post("/api/teams/assign-skills")
async def assign_skills_to_team(request: AssignTeamSkillsRequest, db: Session = Depends(get_db), token: str = Depends(prof_or_ta_required)):
    """Assign skills to a team"""
    try:
        team = db.query(Team).filter(Team.id == request.team_id).first()
        if not team:
            raise HTTPException(status_code=404, detail="Team not found")
        
        # Get all skills by IDs
        skills = db.query(Skill).filter(Skill.id.in_(request.skill_ids)).all()
        if len(skills) != len(request.skill_ids):
            raise HTTPException(status_code=400, detail="Some skill IDs are invalid")
        
        # Clear existing skills and assign new ones
        team.skills = skills
        db.commit()
        
        return JSONResponse(status_code=200, content={
            "message": "Skills assigned successfully to team",
            "team_id": team.id,
            "skill_count": len(skills)
        })
    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error assigning skills to team: {str(e)}")


@app.post("/create-skill")
def create_skill( skill_req: SkillRequest):
    return {"bgColor" : skill_req.bgColor}


@app.get("/teams/FormedTeams")
def setFormedTeams(db: Session = Depends(get_db)):
    teams = db.query(Team).all()

    return_data = []
    for team in teams:
        team_data = {
            "number": team.id,
            "name": team.name,
            "details": "",  # Add details if needed
            "members": [member.name for member in team.members]  # Extract member names
        }
        return_data.append(team_data)

    return return_data

@app.get("/teams/betaTestPairs")
def setbetaTestPairs(db: Session = Depends(get_db)):
    teams = db.query(Team).all()

    return_data = []
    for team in teams:
        team_data = {
            "number": team.id,
            "name": team.name,
            "details": "",  # Add details if needed
            "members": [member.name for member in team.members]  # Extract member names
        }
        return_data.append(team_data)

    return return_data

@app.get("/gradeables/")
async def get_gradeable_table(
    db: Session = Depends(get_db),
    #token: str = Depends(prof_or_ta_required)
):
    """
    Get the gradeable table for professors and TAs
    """
    gradeables = db.query(Gradeable).all()
    results = []
    for gradeable in gradeables:
        results.append({
            "id": gradeable.id,
            "title": gradeable.title,
            "description": gradeable.description,
            "due_date": gradeable.due_date,
            "max_points": gradeable.max_points,
            "creator_id": gradeable.creator_id,
            "created_at": gradeable.created_at
        })
    return JSONResponse(status_code=200, content=results)

@app.get("/gradeables/{gradeable_id}")
async def get_gradeable_by_id(
    gradeable_id: int,
    db: Session = Depends(get_db),
    # token: str = Depends(prof_or_ta_required)
):
    """
    Get a specific gradeable by ID
    """
    gradeable = db.query(Gradeable).filter(Gradeable.id == gradeable_id).first()
    if not gradeable:
        raise HTTPException(status_code=404, detail="Gradeable not found")
    
    return JSONResponse(status_code=200, content={
        "id": gradeable.id,
        "title": gradeable.title,
    })
@app.get("/gradeables/{gradeable_id}/scores")
async def get_gradeable_submissions(
    gradeable_id: int,
    db: Session = Depends(get_db),
    # token: str = Depends(prof_or_ta_required)
):
    """
    Get all submissions for a specific gradeable
    """
    submissions = db.query(GradeableScores).filter(GradeableScores.gradeable_id == gradeable_id).all()
    results = []
    for submission in submissions:
        results.append({
            "id": submission.id,
            "user_id": submission.user_id,
            "name": submission.user.name,
            "gradeable_id": submission.gradeable_id,
            "user_id": submission.user_id, 
            "name": submission.user.name,
            #"submitted_at": submission.submitted_at,
            "score": submission.score
        })
    return JSONResponse(status_code=200, content=results)

@app.post("/gradeables/{gradeable_id}/upload-scores")
async def upload_gradeable_scores(
    gradeable_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    token: str = Depends(prof_or_ta_required)
):
    """
    Upload scores for a specific gradeable
    """
    # Ensure the file is a CSV
    if not file.filename.endswith('.csv'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only CSV files are allowed"
        )
    
    try:
        # Validate gradeable exists and get max points
        gradeable = db.query(Gradeable).filter(Gradeable.id == gradeable_id).first()
        if not gradeable:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Gradeable not found"
            )
        
        # Read and parse file content
        content = await file.read()
        content_str = content.decode('utf-8')
        
        # Parse scores with detailed validation
        scores = parse_scores_from_csv(
            csv_content=content_str, 
            gradeable_id=gradeable_id, 
            max_points=gradeable.max_points,
            db=db
        )
        
        # Bulk upsert scores
        for score_data in scores:
            existing_submission = db.query(GradeableScores).filter(
                GradeableScores.gradeable_id == gradeable_id,
                GradeableScores.user_id == score_data["user_id"]
            ).first()
            
            if existing_submission:
                existing_submission.score = score_data["score"]
            else:
                new_submission = GradeableScores(
                    user_id=score_data["user_id"],
                    gradeable_id=gradeable_id,
                    score=score_data["score"]
                )
                db.add(new_submission)
        
        db.commit()
        
        return JSONResponse(status_code=200, content={
            "message": "Scores uploaded successfully",
            "gradeable_id": gradeable_id,
            "total_submissions": len(scores)
        })
    
    except ValueError as ve:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Unexpected error uploading scores: {str(e)}")
        
        

@app.post("/gradeables/create")
async def create_gradeable(
    gradeable: GradeableCreateRequest,
    user_data: User = Depends(prof_or_ta_required),
    db: Session = Depends(get_db)
):
    """Create a new gradeable"""
    print("HI")
    username = user_data.get('sub')
    user = db.query(User).filter(User.username == username).first()
    print("2137")
    try:
        print("Title is", gradeable.title, "Max points is", gradeable.max_points, "Creator ID is", user.id)
        new_gradeable = Gradeable(
            title=gradeable.title,
            max_points=gradeable.max_points,
            creator_id=user.id
        )
        
        print("Hello")
        db.add(new_gradeable)
        db.commit()
        db.refresh(new_gradeable)
        print("HELLO")

        
        return JSONResponse(status_code=201, content={
            #"id": new_gradeable.id,
            "title": new_gradeable.title,
            "max_points": new_gradeable.max_points,
            "creator_id": new_gradeable.creator_id,
        })
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error creating gradeable: {str(e)}"
        )

def parse_scores_from_csv(csv_content: str, 
    gradeable_id: int, 
    max_points: int,
    db: Session) -> List[Dict[str, Any]]:
    """
    Parse CSV content containing user scores.
    Expected CSV format: user_id,score
    First row should be headers.
    
    Also assigns a default score of 0 to any student who doesn't have a score in the CSV.
    
    Returns:
        List of dictionaries with user_id and score
    """
    # import csv
    # from io import StringIO
    
    scores = []
    processed_usernames = set()
    
    # Parse the CSV content
    try:
        csv_file = StringIO(csv_content)
        csv_reader = csv.DictReader(csv_file)
        
        # Check required headers
        required_headers = ['id','username', 'score']
        headers = csv_reader.fieldnames
        print("headers are", headers)
        # if not all(header in headers for header in required_headers):
        #     print(f"Warning: Extra headers found: {headers}. Proceeding with parsing.")
        #     raise ValueError(f"CSV must contain headers: {', '.join(required_headers)}")
        print("line")
        # Process each row
        for row_num, row in enumerate(csv_reader, start=2):
            print("hihfi")
            print("Row is", row)
            try:
                username = row['username'].strip()
                score = int(row['score'])
                
                user = db.query(User).filter(User.username == username).first()
                if not user:
                    raise ValueError(f"User with username '{username}' not found on row {row_num}")

                print("User ID is", user_id, "Score is", score)
                scores.append({
                    'user_id': user_id,
                    'score': score
                })
                processed_usernames.add(username)
            except (ValueError, KeyError) as e:
                # Skip invalid rows but continue processing
                print(f"Error processing row: {row}. Error: {str(e)}")
                continue
    
    except Exception as e:
        raise ValueError(f"Error parsing CSV: {str(e)}")
    
    # Get all students from the database and add default score of 0 for missing ones
        # Get student role ID
    student_role = db.query(Role).filter(Role.role == RoleType.STUDENT).first()
    if student_role:
        students = db.query(User).filter(User.role_id == student_role.id).all()
        
        for student in students:
            if student.id not in processed_user_ids:
                scores.append({
                    'user_id': student.id,
                    'score': 0
                })
    
    return scores


# submittables start here 
# this is to submit file for a submittable, done by students
@app.post("/submittables/{submittable_id}/submit")
async def submit_file(
    submittable_id: int,
    file: UploadFile = File(...),  # Now accepts a single file
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Submit a file for a submittable.
    Only one submission per submittable per team is allowed.
    """
    # Get the submittable
    submittable = db.query(Submittable).filter(Submittable.id == submittable_id).first()
    if not submittable:
        raise HTTPException(status_code=404, detail="Submittable not found")

    # Get the user's team
    user = db.query(User).filter(User.id == current_user["user"].id).first()
    if not user or not user.team_id:
        raise HTTPException(status_code=400, detail="User must be part of a team to submit")

    # Check if team already has a submission
    existing_submission = db.query(Submission).filter(
        Submission.team_id == user.team_id,
        Submission.submittable_id == submittable_id
    ).first()

    if existing_submission:
        raise HTTPException(
            status_code=400, 
            detail="Your team has already submitted a file for this submittable. Please delete the existing submission first."
        )

    # Check if submission is allowed based on opens_at and deadline
    now = datetime.now(timezone.utc)
    opens_at = datetime.fromisoformat(submittable.opens_at) if submittable.opens_at else None
    deadline = datetime.fromisoformat(submittable.deadline)

    if opens_at and now < opens_at:
        raise HTTPException(status_code=400, detail="Submission period has not started yet")
    if now > deadline:
        raise HTTPException(status_code=400, detail="Submission deadline has passed")

    # Generate a unique filename
    file_extension = os.path.splitext(file.filename)[1]
    unique_filename = f"submission_{uuid.uuid4()}{file_extension}"
    file_path = os.path.join("uploads", unique_filename)

    # Save the file
    try:
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")

    # Create submission record
    submission = Submission(
        team_id=user.team_id,
        file_url=file_path,
        original_filename=file.filename,
        submittable_id=submittable_id,
        score=None  # Initialize score as None since it hasn't been graded yet
    )

    try:
        db.add(submission)
        db.commit()
        db.refresh(submission)
        return {
            "message": "File submitted successfully",
            "submission_id": submission.id,
            "original_filename": submission.original_filename,
            "max_score": submittable.max_score,  # Include max_score in response
            "score": submission.score  # Include current score (will be None for new submissions)
        }
    except Exception as e:
        # If database operation fails, delete the uploaded file
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=500, detail=f"Failed to create submission record: {str(e)}")

# this is to download the file for a submission, done by profs and students
@app.get("/submissions/{submission_id}/download")
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
        if role == RoleType.PROF:
            # Professors can download any submission
            pass
        elif role == RoleType.STUDENT:
            # Students can only download their team's submission
            if not user.team_id or user.team_id != submission.team_id:
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

# this is to get all submittables categorized by status, done by students and profs
@app.get("/submittables/")
async def get_submittables(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get all submittables categorized by status"""
    try:
        # Get all submittables
        submittables = db.query(Submittable).all()
        
        # Get user's team submissions
        user = current_user["user"]
        team_submissions = {}
        if user.team_id:
            submissions = db.query(Submission).filter(Submission.team_id == user.team_id).all()
            team_submissions = {s.submittable_id: s for s in submissions}
        
        # Helper function to format submittable
        def format_submittable(s):
            submission = team_submissions.get(s.id)
            return {
                "id": s.id,
                "title": s.title,
                "description": s.description,
                "opens_at": s.opens_at,
                "deadline": s.deadline,
                "max_score": s.max_score,  # Add max_score from submittable
                "reference_files": [{
                    "original_filename": s.original_filename
                }] if s.file_url else [],
                "submission_status": {
                    "has_submitted": bool(submission),
                    "submission_id": submission.id if submission else None,
                    "submitted_on": submission.submitted_on if submission else None,
                    "original_filename": submission.original_filename if submission else None,
                    "score": submission.score if submission else None  # Add score from submission
                }
            }

        # Categorize submittables
        now = datetime.now(timezone.utc)
        upcoming = []
        open_submittables = []
        closed = []

        for s in submittables:
            formatted = format_submittable(s)
            opens_at = datetime.fromisoformat(s.opens_at) if s.opens_at else None
            deadline = datetime.fromisoformat(s.deadline)

            if opens_at and now < opens_at:
                upcoming.append(formatted)
            elif now > deadline:
                closed.append(formatted)
            else:
                open_submittables.append(formatted)

        return {
            "upcoming": upcoming,
            "open": open_submittables,
            "closed": closed
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching submittables: {str(e)}")

# this is to download the reference file for a submittable, done by students and profs
@app.get("/submittables/{submittable_id}/reference-files/download")
async def download_reference_file(
    submittable_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Download a reference file for a submittable"""
    try:
        # Get the submittable
        submittable = db.query(Submittable).filter(Submittable.id == submittable_id).first()
        if not submittable:
            raise HTTPException(status_code=404, detail="Submittable not found")

        if not submittable.file_url:
            raise HTTPException(status_code=404, detail="No reference file found")

        # Check if file exists
        if not os.path.exists(submittable.file_url):
            raise HTTPException(status_code=404, detail="File not found on server")

        # Return the file
        return FileResponse(
            submittable.file_url,
            media_type='application/octet-stream',
            filename=submittable.original_filename
        )

    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error downloading file: {str(e)}")

# this is to create a new submittable, done by profs
@app.post("/submittables/create")
async def create_submittable(
    title: str = FastAPIForm(...),
    deadline: str = FastAPIForm(...),
    description: str = FastAPIForm(...),
    max_score: int = FastAPIForm(...),  # Add max_score parameter
    opens_at: Optional[str] = FastAPIForm(None),
    file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    token: str = Depends(prof_required)
):
    """Create a new submittable with an optional reference file"""
    try:
        # Basic validation
        try:
            deadline_dt = datetime.fromisoformat(deadline.replace('Z', '+00:00'))
            if opens_at:
                opens_at_dt = datetime.fromisoformat(opens_at.replace('Z', '+00:00'))
                # Validate that opens_at is before deadline
                if opens_at_dt >= deadline_dt:
                    raise HTTPException(
                        status_code=400, 
                        detail="opens_at must be before deadline"
                    )
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format")
            
        # Validate max_score
        if max_score <= 0:
            raise HTTPException(status_code=400, detail="Maximum score must be greater than zero")
            
        # Get the creator (professor) from token
        payload = token  # The token is already decoded by prof_required dependency
        username = payload.get("sub")
        user = db.query(User).filter(User.username == username).first()
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Create submittable object
        submittable = Submittable(
            title=title,
            deadline=deadline,
            description=description,
            max_score=max_score,  # Add max_score to submittable creation
            opens_at=opens_at,
            creator_id=user.id,
            file_url="",  # Default empty string
            original_filename=""  # Default empty string
        )

        # Handle file upload if provided
        if file:
            # Create uploads directory if it doesn't exist
            upload_dir = "uploads"
            if not os.path.exists(upload_dir):
                os.makedirs(upload_dir)

            # Generate unique filename
            file_extension = os.path.splitext(file.filename)[1]
            unique_filename = f"{uuid.uuid4()}{file_extension}"
            file_path = os.path.join(upload_dir, unique_filename)

            # Save file
            with open(file_path, "wb") as buffer:
                content = await file.read()
                buffer.write(content)

            # Update submittable with file information
            submittable.file_url = file_path
            submittable.original_filename = file.filename

        # Add to database
        db.add(submittable)
        db.commit()
        db.refresh(submittable)

        # Return JSON response with proper structure
        return JSONResponse(
            status_code=201,
            content={
                "message": "Submittable created successfully",
                "submittable": {
                    "id": submittable.id,
                    "title": submittable.title,
                    "opens_at": submittable.opens_at,
                    "deadline": submittable.deadline,
                    "description": submittable.description,
                    "max_score": submittable.max_score,  # Include max_score in response
                    "created_at": submittable.created_at,
                    "reference_files": [{
                        "original_filename": submittable.original_filename
                    }] if submittable.file_url else [],
                    "submission_status": {
                        "has_submitted": False,
                        "submission_id": None,
                        "submitted_on": None,
                        "original_filename": None,
                        "score": None  # Include score field in submission status
                    }
                }
            }
        )

    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error creating submittable: {str(e)}")

# this is to get details of a specific submittable, done by students and profs
@app.get("/submittables/{submittable_id}")
async def get_submittable(
    submittable_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get details of a specific submittable"""
    try:
        submittable = db.query(Submittable).filter(Submittable.id == submittable_id).first()
        if not submittable:
            raise HTTPException(status_code=404, detail="Submittable not found")
        
        return JSONResponse(status_code=200, content={
            "id": submittable.id,
            "title": submittable.title,
            "opens_at": submittable.opens_at,
            "deadline": submittable.deadline,
            "description": submittable.description,
            "max_score": submittable.max_score,
            "created_at": submittable.created_at,
            "reference_file": {
                "file_url": submittable.file_url,
                "original_filename": submittable.original_filename
            } if submittable.file_url else None
        })
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching submittable: {str(e)}")

# this is to get all submissions for a submittable, done by profs
@app.get("/submittables/{submittable_id}/submissions")
async def get_submittable_submissions(
    submittable_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get all submissions for a submittable (professors only)"""
    try:
        if current_user["role"] != RoleType.PROF:
            raise HTTPException(status_code=403, detail="Only professors can view all submissions")
        
        submittable = db.query(Submittable).filter(Submittable.id == submittable_id).first()
        if not submittable:
            raise HTTPException(status_code=404, detail="Submittable not found")
        
        submissions = db.query(Submission).filter(Submission.submittable_id == submittable_id).all()
        
        result = []
        for submission in submissions:
            submission_data = {
                "id": submission.id,
                "team_id": submission.team_id,
                "submitted_on": submission.submitted_on,
                "score": submission.score,
                "max_score": submittable.max_score,
                "file": {
                    "file_url": submission.file_url,
                    "original_filename": submission.original_filename
                }
            }
            result.append(submission_data)
        
        return JSONResponse(status_code=200, content=result)
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching submissions: {str(e)}")

# this is to delete a submittable and all its submissions, done by profs
@app.delete("/submittables/{submittable_id}")
async def delete_submittable(
    submittable_id: int,
    db: Session = Depends(get_db),
    token: str = Depends(prof_required)
):
    """Delete a submittable and all its submissions (professors only)"""
    try:
        submittable = db.query(Submittable).filter(Submittable.id == submittable_id).first()
        if not submittable:
            raise HTTPException(status_code=404, detail="Submittable not found")
        
        # Delete the reference file if it exists
        if submittable.file_url:
            local_path = submittable.file_url.lstrip('/')
            if os.path.exists(local_path):
                os.remove(local_path)
        
        # Delete all submission files
        submissions = db.query(Submission).filter(Submission.submittable_id == submittable_id).all()
        for submission in submissions:
            if submission.file_url:
                local_path = submission.file_url.lstrip('/')
                if os.path.exists(local_path):
                    os.remove(local_path)
        
        # Delete all submissions
        db.query(Submission).filter(Submission.submittable_id == submittable_id).delete()
        
        # Delete the submittable
        db.delete(submittable)
        db.commit()
        
        return JSONResponse(status_code=200, content={"message": "Submittable deleted successfully"})
    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error deleting submittable: {str(e)}")

# this is to update a submittable, done by profs
@app.put("/submittables/{submittable_id}")
async def update_submittable(
    submittable_id: int,
    title: str = FastAPIForm(...),
    deadline: str = FastAPIForm(...),
    description: str = FastAPIForm(...),
    max_score: int = FastAPIForm(...),
    opens_at: Optional[str] = FastAPIForm(None),
    file: Optional[UploadFile] = None,
    db: Session = Depends(get_db),
    token: str = Depends(prof_required)
):
    """Update a submittable (professors only)"""
    try:
        # Basic validation
        try:
            deadline_dt = datetime.fromisoformat(deadline.replace('Z', '+00:00'))
            if opens_at:
                opens_at_dt = datetime.fromisoformat(opens_at.replace('Z', '+00:00'))
                # Validate that opens_at is before deadline
                if opens_at_dt >= deadline_dt:
                    raise HTTPException(
                        status_code=400, 
                        detail="opens_at must be before deadline"
                    )
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format")
            
        # Validate max_score
        if max_score <= 0:
            raise HTTPException(status_code=400, detail="Maximum score must be greater than zero")
            
        existing_submittable = db.query(Submittable).filter(Submittable.id == submittable_id).first()
        if not existing_submittable:
            raise HTTPException(status_code=404, detail="Submittable not found")
        
        # Update basic information
        existing_submittable.title = title
        existing_submittable.opens_at = opens_at
        existing_submittable.deadline = deadline
        existing_submittable.description = description
        existing_submittable.max_score = max_score
        
        # Handle file update if provided
        if file:
            # Delete old file if it exists
            if existing_submittable.file_url:
                old_file_path = existing_submittable.file_url.lstrip('/')
                if os.path.exists(old_file_path):
                    os.remove(old_file_path)
            
            # Save new file
            file_extension = file.filename.split('.')[-1]
            file_name = f"ref_{uuid.uuid4()}.{file_extension}"
            file_path = f"uploads/{file_name}"
            
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            
            existing_submittable.file_url = f"/uploads/{file_name}"
            existing_submittable.original_filename = file.filename
        
        db.commit()
        db.refresh(existing_submittable)
        
        return JSONResponse(status_code=200, content={
            "message": "Submittable updated successfully",
            "submittable_id": existing_submittable.id
        })
    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)  # Clean up file if something went wrong
        raise HTTPException(status_code=500, detail=f"Error updating submittable: {str(e)}")

# this is to delete a submission, done by profs or the student who submitted        
@app.delete("/submissions/{submission_id}")
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
        if current_user["role"] != RoleType.PROF:
            # For students, check if they belong to the team that submitted
            if user.team_id != submission.team_id:
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
        raise HTTPException(status_code=500, detail=f"Error deleting submission: {str(e)}")

# this is to grade a submission, done by profs
@app.put("/submissions/{submission_id}/grade")
async def grade_submission(
    submission_id: int,
    score: int = FastAPIForm(...),
    db: Session = Depends(get_db),
    token: str = Depends(prof_required)
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

##Chatting Routes

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/forums_uploads", StaticFiles(directory="forums_uploads"), name="forums_uploads")    

class ConnectionManager:
    def __init__(self):
        self.rooms: Dict[str, List[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket, channel_id: int, user_id: int):
        await websocket.accept()
        room_name = f"channel_{channel_id}"
        
        if room_name not in self.rooms:
            self.rooms[room_name] = []
        
        self.rooms[room_name].append(websocket)
        websocket.user_id = user_id
    
    def disconnect(self, websocket: WebSocket, channel_id: int):
        room_name = f"channel_{channel_id}"
        if room_name in self.rooms:
            self.rooms[room_name].remove(websocket)
            if not self.rooms[room_name]:
                del self.rooms[room_name]
    
    async def broadcast(self, message: str, channel_id: int):
        room_name = f"channel_{channel_id}"
        if room_name in self.rooms:
            dead_connections = []
            for connection in self.rooms[room_name]:
                try:
                    await connection.send_text(message)
                except WebSocketDisconnect:
                    dead_connections.append(connection)
            
            for conn in dead_connections:
                self.rooms[room_name].remove(conn)

manager = ConnectionManager()

# Pydantic models for request/response
class MessageModel(BaseModel):
    content: str
    channel_id: int
    sender_id: int
    message_type: str = 'text'
    file_data: Optional[str] = None
    file_name: Optional[str] = None

# Routes
@app.post("/discussions")
async def get_discussions_page(
    current_user_data: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user = current_user_data["user"]
    if not user:
        raise HTTPException(status_code=404, detail=f"User not found: {user.name}")

    channels = []
    
    # Add global channel for all users
    global_channel = db.query(Channel).filter(Channel.type == 'global').first()
    if global_channel:
        channels.append(global_channel)
    
    # For students: add their team channel and team-TA channel if they exist
    if user.role.role == RoleType.STUDENT and user.teams:
        team = user.teams[0]  # Get the student's team
        
        # Get or create team channel
        team_channel = db.query(Channel).filter(
            Channel.type == 'team',
            Channel.team_id == team.id
        ).first()
        
        if not team_channel:
            team_channel = Channel(
                name=f'Team {team.name} Chat',
                type='team',
                team_id=team.id
            )
            db.add(team_channel)
            db.commit()
        
        channels.append(team_channel)
        
        # Check if team has TA(s) and add team-TA channel if it exists
        team_ta = db.query(Team_TA).filter(Team_TA.team_id == team.id).first()
        if team_ta:
            ta_channel = db.query(Channel).filter(
                Channel.type == 'ta-team',
                Channel.team_id == team.id
            ).first()
            
            if not ta_channel:
                ta_channel = Channel(
                    name=f'Team {team.name} TA Channel',
                    type='ta-team',
                    team_id=team.id
                )
                db.add(ta_channel)
                db.commit()
            
            channels.append(ta_channel)
    
    # For TAs and Profs: add all their team-TA channels
    elif user.role.role in [RoleType.TA, RoleType.PROF]:
        # Get all teams this TA/Prof is assigned to
        team_tas = db.query(Team_TA).filter(Team_TA.ta_id == user.id).all()
        for team_ta in team_tas:
            ta_channel = db.query(Channel).filter(
                Channel.type == 'ta-team',
                Channel.team_id == team_ta.team_id
            ).first()
            
            if not ta_channel:
                team = db.query(Team).filter(Team.id == team_ta.team_id).first()
                ta_channel = Channel(
                    name=f'Team {team.name} TA Channel',
                    type='ta-team',
                    team_id=team.id
                )
                db.add(ta_channel)
                db.commit()
            
            channels.append(ta_channel)

    return {
        "id": user.id,
        "name": user.name,
        "username": user.username,
        "team_id": user.team_id,
        "team_name": user.teams[0].name if user.teams else 'No Team',
        "is_ta": user.role.role in [RoleType.TA, RoleType.PROF],
        "channels": channels,
        "role": user.role.role.value
    }

def validate_channel_access(user: User, channel_id: int, db: Session) -> bool:
    """
    Validates whether a user has access to a specific channel.
    
    Args:
        user: The User object
        channel_id: The ID of the channel to check
        db: Database session
    
    Returns:
        bool: True if user has access, False otherwise
    """
    # Get the channel
    channel = db.query(Channel).filter(Channel.id == channel_id).first()
    if not channel:
        return False
        
    # Global channel is accessible to all
    if channel.type == 'global':
        return True
        
    # For team channels:
    if channel.type == 'team':
        # # If user is a professor, allow access
        # if user.role.role == RoleType.PROF:
        #     return True
        # For students and TAs, check if they're in the team
        #return any(team.id == channel.team_id for team in user.teams)
        return user.team_id == channel.team_id
        
    # For TA-team channels:
    if channel.type == 'ta-team':
        # # If user is a professor, allow access
        # if user.role.role == RoleType.PROF:
        #     return True
        # If user is a TA, check if they're assigned to the team
        if user.role.role == RoleType.TA:
            ta_assignment = db.query(Team_TA).filter(
                Team_TA.team_id == channel.team_id,
                Team_TA.ta_id == user.id
            ).first()
            return ta_assignment is not None
        # If user is a student, check if they're in the team
        if user.role.role == RoleType.STUDENT:
            #return any(team.id == channel.team_id for team in user.teams)
            return user.team_id == channel.team_id  
            
    return False

@app.get("/discussions/channels/{channel_id}/messages")
async def get_messages(
    channel_id: int,
    current_user_data: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user = current_user_data["user"]
    
    # Validate user's access to the channel
    if not validate_channel_access(user, channel_id, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this channel"
        )
    
    messages = db.query(Message).filter(
        Message.channel_id == channel_id
    ).order_by(Message.created_at).all()
    
    # Convert messages to dictionary with sender information
    return [
        {
            "id": message.id,
            "content": message.content,
            "sender_id": message.sender_id,
            "sender_name": message.sender.name,
            "channel_id": message.channel_id,
            "created_at": message.created_at.isoformat(),
            "message_type": message.message_type,
            "file_name": message.file_name
        } for message in messages
    ]

@app.post("/discussions/messages")
async def send_message(
    message: MessageModel,
    current_user_data: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
): 
    user = current_user_data["user"]

    if(message.sender_id != user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You cannot send messages on behalf of another user"
        )
    
    # Validate user's access to the channel
    if not validate_channel_access(user, message.channel_id, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this channel"
        )

    try:
        file_path = None
        if message.message_type == 'file' and message.file_data:
            file_data = base64.b64decode(message.file_data)
            file_name = f"{uuid.uuid4()}_{message.file_name}"
            file_path = os.path.join("forums_uploads", file_name)
            with open(file_path, "wb") as f:
                f.write(file_data)
            message.content = file_name  # Store just the filename, not the full path

        new_message = Message(
            content=message.content,
            sender_id=user.id,
            channel_id=message.channel_id,
            message_type=message.message_type,
            file_name=message.content if message.message_type == 'file' else None  # Use content as file_name for files
        )
        db.add(new_message)
        db.commit()
        db.refresh(new_message)

        # Format message for broadcasting
        message_data = {
            "id": new_message.id,
            "content": new_message.content,
            "sender_id": new_message.sender_id,
            "sender_name": new_message.sender.name,
            "channel_id": new_message.channel_id,
            "created_at": new_message.created_at.isoformat(),
            "message_type": new_message.message_type,
            "file_name": new_message.content if message.message_type == 'file' else None  # Use content as file_name for files
        }

        await manager.broadcast(
            json.dumps(message_data),
            message.channel_id
        )

        return message_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.websocket("/discussions/ws/{channel_id}/{token}")
async def websocket_endpoint(
    websocket: WebSocket, 
    channel_id: int, 
    #user_id: int,
    token: str,
    # current_user_data: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # print("In here")
    current_user_data = get_current_user_from_string(token , db)
    if not current_user_data:
        raise HTTPException(status_code=401, detail="Invalid authentication credentials")
    user = current_user_data["user"]
    
    # Validate user's access to the channel
    print(f"User: {user.username}, Channel ID: {channel_id}")
    if not validate_channel_access(user, channel_id, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this channel"
        )

    #await manager.connect(websocket, channel_id, int(token))
    

    await manager.connect(websocket, channel_id, user.id)
    try:
        while True:
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, channel_id)

@app.get("/discussions/download/{file_name}")
async def download_file(
    file_name: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Download a file and return it as base64 encoded data"""
    try:
        # Get the file record from the database
        file_record = db.query(Message).filter(Message.file_name == file_name).first()
        if not file_record:
            raise HTTPException(status_code=404, detail="File not found")
        
        # Check if the user has access to the file
        user = current_user["user"]
        if not validate_channel_access(user, file_record.channel_id, db):
            raise HTTPException(status_code=403, detail="Not authorized to download this file")
        # Check if the file is a reference file
        if file_record.message_type != 'file':
            raise HTTPException(status_code=400, detail="Not a reference file")
        
        # Convert URL path to local path
        local_path = file_record.file_name.lstrip('/')
        local_path = os.path.join("forums_uploads", local_path)
        # Check if the file exists locally
        if not os.path.exists(local_path):
            raise HTTPException(status_code=404, detail="File not found")
        
        # Read the file and encode it in base64
        with open(local_path, "rb") as file:
            file_data = file.read()
            encoded_file_data = base64.b64encode(file_data).decode('utf-8')
        
        return JSONResponse(status_code=200, content={
            "file_id": file_record.id,
            "original_filename": file_record.file_name,
            "file_data": encoded_file_data
        })
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error downloading file: {str(e)}")


from sqlalchemy.orm import Session

@app.post("/teams/upload-csv/")
async def upload_csv(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="Invalid file format. Please upload a CSV file.")

    try:
        # Save the uploaded file to a temporary location
        temp_file_path = f"temp_{file.filename}"
        with open(temp_file_path, "wb") as temp_file:
            temp_file.write(file.file.read())

        # Read the CSV file using pandas
        df = pd.read_csv(temp_file_path)

        # Validate the CSV format
        required_columns = ['team_name', 'member1', 'member2', 'member3', 'member4', 'member5', 'member6', 'member7', 'member8', 'member9', 'member10']
        print(df.columns)
        for _column_name in required_columns:
            if _column_name not in df.columns:
                raise HTTPException(status_code=400, detail=f"Invalid CSV format. Missing column: {_column_name}")

        # Check if all members exist in the Users database and perform other checks
        team_names = set()
        members_set = list()
        for _, row in df.iterrows():
            team_name = row['team_name']
            members = []
            for i in range(1, 11):
                members.append(row[f'member{i}'])

            # members = [row[f'member{i}'] for i in range(1, 11) if pd.notna(row[f'member{i}'])]

            if team_name in team_names:
                raise HTTPException(status_code=400, detail=f"Invalid file: Duplicate team name '{team_name}' found.")
            
            team_names.add(team_name)

            for member_name in members:
                user = db.query(User).filter_by(username=member_name).first()
                if not user:
                    raise HTTPException(status_code=400, detail=f"Invalid file: User '{member_name}' does not exist in the database.")
                if user.team_id:
                    raise HTTPException(status_code=400, detail=f"Invalid file: User '{member_name}' is already assigned to a team.")
                if member_name in members_set:
                    raise HTTPException(status_code=400, detail=f"Invalid file: User '{member_name}' is assigned to multiple teams.")
            members_set.append(members)

        # Get the highest team ID present in the database
        # max_team_id = db.query(func.max(Team.id)).scalar() or 0


        team_names = list(team_names)
        print("Team names: ", team_names)
        print("Members set:", members_set)
        for i in range(len(team_names)):
            team_name = team_names[i]
            members = members_set[i]
            team = Team(name = team_name)
            db.add(team)
            for member in members:
                user = db.query(User).filter_by(username=member).first()
                print("Over here")
                if user:
                    team.members.append(user)
                    user.team_id = team.id
        db.commit()

        
        # Process each row in the CSV file
        # for _, row in 
        #     team_name = row['team_name']
        #     members = []
        #     for i in range(10):
        #         print(row[f'member{i}'])
        #         members.append(row[f'member{i}'])
        #     print(members)
        #     # Create a new team
        #     team = Team(name=team_name)
        #     db.add(team)

        #     # Add members to the team
        #     for member_name in members:
        #         user = db.query(User).filter_by(name=member_name).first()
        #         if user:
        #             # check if user is in team already
        #             # if user not in team.members:
        #             #     # check if user is already in a team
        #             #     if user.team_id is None:
        #             #         # Add the user to the team
        #             team.members.append(user)
        #             user.team_id = team.id  # Assign the team ID to the user
        #             print("Added user to team:", user.name, "in team:", team.name)
        # print("Committed the changes")
        # db.commit()

        # Clean up the temporary file
        os.remove(temp_file_path)

        return {"detail": "File uploaded and data saved successfully!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# __________________________________
#            OTP Flow
# __________________________________



# Pydantic models for forgot password flow
class RequestOTPModel(BaseModel):
    email: EmailStr

class VerifyOTPModel(BaseModel):
    email: EmailStr
    otp: str

class ResetPasswordWithOTPModel(BaseModel):
    email: EmailStr
    otp: str
    new_password: str
    confirm_password: str

# Generate a cryptographically secure OTP
def generate_secure_otp(length=6):
    """Generate a cryptographically secure random OTP of specified length"""
    # Use secrets module for cryptographic security
    return ''.join(secrets.choice(string.digits) for _ in range(length))

# Hash an OTP for secure storage
def hash_otp(otp: str) -> str:
    """Hash an OTP using the same password hashing mechanism"""
    return pwd_context.hash(otp)

# Verify a provided OTP against its hash
def verify_otp(plain_otp: str, hashed_otp: str) -> bool:
    """Verify an OTP against its hashed value"""
    return pwd_context.verify(plain_otp, hashed_otp)

# Generate a secure random string for passwords
def generate_secure_string(length=10):
    """Generate a cryptographically secure random string for temporary passwords"""
    alphabet = string.ascii_letters + string.digits + string.punctuation
    return ''.join(secrets.choice(alphabet) for _ in range(length))

# Replace the previous OTP storage dictionary with database operations
# OTP Request endpoint
@app.post("/request-otp")
async def request_otp(request: RequestOTPModel, db: Session = Depends(get_db)):
    """
    Request OTP for password reset and send it via email
    """
    try:
        # Check if user with email exists
        user = db.query(User).filter(User.email == request.email).first()
        
        if not user:
            # For security, we still return the same message
            # but we'll log this for debugging
            print(f"OTP request for non-existent email: {request.email}")
            return {
                "message": "If the email exists in our system, a verification code has been sent. Please check your spam folder if you don't see it in your inbox.",
                "status": "email_not_found"  # Add a status for debugging only
            }
        
        # Generate secure OTP
        plain_otp = generate_secure_otp(6)
        print(f"Generated OTP for {user.email}: {plain_otp}")  # Only log during development
        
        # Hash the OTP for secure storage
        hashed_otp = hash_otp(plain_otp)
        
        # Set expiration time (10 minutes from now)
        expiration_time = datetime.now(timezone.utc) + timedelta(minutes=10)
        
        # Check if an OTP entry already exists for this user
        existing_otp = db.query(UserOTP).filter(UserOTP.user_id == user.id).first()
        
        if existing_otp:
            # Update existing OTP record
            existing_otp.hashed_otp = hashed_otp
            existing_otp.expires_at = expiration_time.isoformat()
        else:
            # Create new OTP record
            new_otp_record = UserOTP(
                user_id=user.id,
                hashed_otp=hashed_otp,
                expires_at=expiration_time.isoformat()
            )
            db.add(new_otp_record)
        
        # Commit the changes
        db.commit()
        
        # Create email content
        email_subject = "Your Password Reset Code - Sahara"
        email_html = create_otp_email(plain_otp)
        
        # Send email with OTP
        try:
            print(f"Attempting to send email to {user.email} with OTP: {plain_otp}")
            email_sent = send_email(user.email, email_subject, email_html)
        except Exception as e:
            print(f"Exception during email sending: {str(e)}")
            print(traceback.format_exc())
            email_sent = False
        
        if not email_sent:
            print(f"Failed to send OTP email to {user.email}")
            return {
                "message": "If the email exists in our system, a verification code has been sent. Please check your spam folder if you don't see it in your inbox.",
                "status": "email_attempted" # For debugging purposes
            }
        
        # For security reasons, always return the same message whether email exists or not
        return {
            "message": "If the email exists in our system, a verification code has been sent. Please check your spam folder if you don't see it in your inbox.",
            "status": "email_sent" # For debugging purposes
        }
    
    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        print(f"Error in request_otp: {e}")
        print(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process your request. Please try again."
        )

# Verify OTP endpoint
@app.post("/verify-otp")
async def verify_otp_endpoint(request: VerifyOTPModel, db: Session = Depends(get_db)):
    """
    Verify OTP provided by the user
    """
    try:
        # Find user by email
        user = db.query(User).filter(User.email == request.email).first()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Get OTP record for user
        otp_record = db.query(UserOTP).filter(UserOTP.user_id == user.id).first()
        
        # Check if OTP record exists
        if not otp_record:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No active OTP request found for this email"
            )
        
        # Check if OTP has expired
        expiration_time = datetime.fromisoformat(otp_record.expires_at)
        if datetime.now(timezone.utc) > expiration_time:
            # Delete expired OTP
            db.delete(otp_record)
            db.commit()
            
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="OTP has expired. Please request a new one."
            )
        
        # Verify OTP
        if not verify_otp(request.otp, otp_record.hashed_otp):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid OTP"
            )
        
        # OTP is valid - do not delete yet as we need it for reset_password_with_otp
        return {"message": "OTP verified successfully"}
    
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"Error in verify_otp: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to verify OTP. Please try again."
        )

# Reset password with OTP endpoint
@app.post("/reset-password-with-otp")
async def reset_password_with_otp(request: ResetPasswordWithOTPModel, db: Session = Depends(get_db)):
    """
    Reset password after OTP verification
    """
    try:
        # Find user by email
        user = db.query(User).filter(User.email == request.email).first()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Get OTP record for user
        otp_record = db.query(UserOTP).filter(UserOTP.user_id == user.id).first()
        
        # Check if OTP record exists
        if not otp_record:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No active OTP request found for this email"
            )
        
        # Check if OTP has expired
        expiration_time = datetime.fromisoformat(otp_record.expires_at)
        if datetime.now(timezone.utc) > expiration_time:
            # Delete expired OTP
            db.delete(otp_record)
            db.commit()
            
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="OTP has expired. Please request a new one."
            )
        
        # Verify OTP
        if not verify_otp(request.otp, otp_record.hashed_otp):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid OTP"
            )
        
        # Verify passwords match
        if request.new_password != request.confirm_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Passwords do not match"
            )
        
        # Hash the new password
        hashed_password = create_hashed_password(request.new_password)
        
        # Update user's password
        user.hashed_password = hashed_password
        
        # Delete the OTP record after successful password reset
        db.delete(otp_record)
        
        # Commit changes
        db.commit()
        
        return {"message": "Password reset successfully"}
    
    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        print(f"Error in reset_password_with_otp: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reset password. Please try again."
        )

# Email configuration - you should store these in environment variables in production
EMAIL_HOST = "smtp.gmail.com"
EMAIL_PORT = 587
EMAIL_HOST_USER = "saharaai.noreply@gmail.com"  # Replace with your email
EMAIL_HOST_PASSWORD = "zfrr wwru xeru rbhf"  # Replace with your app password
EMAIL_USE_TLS = True
DEFAULT_FROM_EMAIL = "Sahara Team <saharaai.noreply@gmail.com>"  # Fixed to use the actual email account

# Function to send emails
def send_email(to_email, subject, html_content):
    """
    Send an HTML email using SMTP
    
    Args:
        to_email: Recipient email address
        subject: Email subject
        html_content: HTML body of the email
    """
    try:
        msg = MIMEMultipart()
        msg['From'] = DEFAULT_FROM_EMAIL
        msg['To'] = to_email
        msg['Subject'] = subject
        msg['Date'] = formatdate(localtime=True)
        
        # Attach HTML content
        msg.attach(MIMEText(html_content, 'html'))
        
        print(f"Attempting to send email to {to_email}")
        
        # Connect to SMTP server with more detailed error handling
        try:
            # Enable debug output
            server = smtplib.SMTP(EMAIL_HOST, EMAIL_PORT)
            server.set_debuglevel(1)  # Add this line to enable verbose debug output
            print(f"Connected to SMTP server: {EMAIL_HOST}:{EMAIL_PORT}")
            
            if EMAIL_USE_TLS:
                server.starttls()
                print("TLS encryption enabled")
            
            print(f"Logging in with user: {EMAIL_HOST_USER}")
            server.login(EMAIL_HOST_USER, EMAIL_HOST_PASSWORD)
            print("Login successful")
            
            # Send email - more detailed debugging
            print(f"Sending mail from {EMAIL_HOST_USER} to {to_email}")
            result = server.sendmail(EMAIL_HOST_USER, to_email, msg.as_string())
            print(f"Email sent successfully to {to_email}")
            print(f"Server response: {result if result else 'No response (success)'}")
            server.quit()
            
            return True
        except smtplib.SMTPAuthenticationError as auth_err:
            print(f"SMTP Authentication Error: {str(auth_err)}")
            return False
        except smtplib.SMTPRecipientsRefused as ref_err:
            print(f"Recipients refused: {str(ref_err)}")
            return False
        except smtplib.SMTPSenderRefused as send_err:
            print(f"Sender refused: {str(send_err)}")
            return False
        except smtplib.SMTPDataError as data_err:
            print(f"SMTP data error: {str(data_err)}")
            return False
        except smtplib.SMTPException as smtp_e:
            print(f"SMTP Error: {str(smtp_e)}")
            return False
        except Exception as conn_e:
            print(f"Connection error: {str(conn_e)}")
            print(f"Error type: {type(conn_e).__name__}")
            print(f"Traceback: {traceback.format_exc()}")
            return False
    except Exception as e:
        print(f"Failed to prepare email: {str(e)}")
        print(f"Traceback: {traceback.format_exc()}")
        return False

# Create HTML email template for OTP
def create_otp_email(otp, expiry_minutes=10):
    """
    Create HTML email content for OTP verification
    
    Args:
        otp: The one-time password
        expiry_minutes: Validity period in minutes
    
    Returns:
        HTML content as string
    """
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Password Reset Code</title>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background-color: #4CAF50; color: white; padding: 10px; text-align: center; }}
            .content {{ padding: 20px; background-color: #f9f9f9; }}
            .code {{ font-size: 24px; font-weight: bold; text-align: center; 
                    padding: 15px; background-color: #e9e9e9; margin: 20px 0; letter-spacing: 5px; }}
            .footer {{ font-size: 12px; text-align: center; margin-top: 20px; color: #1f2e6a; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h2>Password Reset Verification</h2>
            </div>
            <div class="content">
                <p>Hello,</p>
                <p>You've requested to reset your password for your Sahara account.</p>
                <p>Please use the following verification code to complete the process:</p>
                
                <div class="code">{otp}</div>
                
                <p>This code is valid for {expiry_minutes} minutes and can only be used once.</p>
                <p>If you didn't request a password reset, please ignore this email or contact support if you have concerns.</p>
            </div>
            <div class="footer">
                <p>This is an automated message, please do not reply directly to this email.</p>
                <p>&copy; {datetime.now().year} Sahara Team</p>
            </div>
        </div>
    </body>
    </html>
    """

import json
# Explicitly import FastAPI's Form and rename it to avoid conflicts
from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, Query, Header, Body, File, Form as FastAPIForm, WebSocket, WebSocketDisconnect, WebSocketException
from fastapi.responses import JSONResponse, Response, FileResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy import ForeignKey, create_engine, Column, Integer, String, Enum, Table, Text, DateTime, text, Float
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
from typing import Optional, List, Annotated
import shutil
import uuid
import json
import csv
from io import StringIO
from fastapi.staticfiles import StaticFiles
from typing import ForwardRef
import base64
import dotenv

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
    opens_at = Column(String, nullable=True)  # ISO 8601 format
    deadline = Column(String, nullable=False)  # ISO 8601 format
    description = Column(String, nullable=False)
    created_at = Column(String, default=datetime.now(timezone.utc).isoformat())
    creator_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    creator = relationship("User", back_populates="submittables")
    submissions = relationship("Submission", back_populates="submittable")
    reference_files = relationship("SubmittableReferenceFile", back_populates="submittable", lazy="joined")


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
    submittable_id = Column(Integer, ForeignKey("submittables.id"), nullable=False)

    team = relationship("Team", back_populates="submissions")
    submittable = relationship("Submittable", back_populates="submissions")
    files = relationship("SubmissionFile", back_populates="submission")

class SubmissionFile(Base):
    __tablename__ = "submission_files"
    id = Column(Integer, primary_key=True)
    submission_id = Column(Integer, ForeignKey("submissions.id"), nullable=False)
    file_url = Column(String, nullable=False)  # URL path to the submitted file
    original_filename = Column(String, nullable=False)  # Original filename of the submitted file

    submission = relationship("Submission", back_populates="files")


class SubmittableReferenceFile(Base):
    __tablename__ = "submittable_reference_files"
    id = Column(Integer, primary_key=True)
    submittable_id = Column(Integer, ForeignKey("submittables.id"), nullable=False)
    file_url = Column(String, nullable=False)  # URL path to the reference file
    original_filename = Column(String, nullable=False)  # Original filename of the reference file
    uploaded_on = Column(String, default=datetime.now(timezone.utc).isoformat())
    creator_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    submittable = relationship("Submittable", back_populates="reference_files")
    creator = relationship("User")

    @validates("creator_id")
    def validate_creator(self, key, value):
        user = SessionLocal.query(User).filter_by(id=value).first()
        if user and user.role.role != RoleType.PROF:
            raise ValueError("Only professors can create reference files.")
        return value


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
    form_responses = relationship("FormResponse", back_populates="user")
    gradeables = relationship("Gradeable", back_populates="creator")
    calendar_events = relationship("UserCalendarEvent", back_populates="creator")
    team_calendar_events = relationship("TeamCalendarEvent", back_populates="creator")
    # global_calendar_events = relationship("GlobalCalendarEvent", back_populates="creator")
    skills = relationship("Skill", secondary=user_skills, back_populates="users")
    gradeable_scores = relationship("GradeableScores", back_populates="user")
    submittables = relationship("Submittable", back_populates="creator", lazy="joined")
    messages = relationship("Message", back_populates="sender")
    quiz_responses = relationship("QuizResponse", back_populates="user")
    
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
            with SessionLocal() as session:
                role = session.query(Role).filter_by(id=self.target_id).first()
                if role and role.name == RoleType.PROFESSOR:
                    raise ValueError("Forms cannot be assigned to Professors.")
        return value

team_members = Table(
    "team_members", Base.metadata,
    Column("team_id", Integer, ForeignKey("teams.id"), primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id"), primary_key=True)
)

class Quiz(Base):
    __tablename__ = "quizzes"
    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    description = Column(String, nullable=True)
    created_at = Column(String, default=datetime.now(timezone.utc).isoformat())
    deadline = Column(String, nullable=False)  # ISO 8601 format
    quiz_json = Column(JSONB, nullable=False)

    responses = relationship("QuizResponse", back_populates="quiz")

class QuizResponse(Base):
    __tablename__ = "quiz_responses"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    quiz_id = Column(Integer, ForeignKey("quizzes.id"), nullable=False)
    submitted_at = Column(String, default=datetime.now(timezone.utc).isoformat())
    quiz_score = Column(Integer, nullable=False)
    response_data = Column(JSONB, nullable=False)  # JSON or serialized response data

    quiz = relationship("Quiz", back_populates="responses")
    user = relationship("User", back_populates="quiz_responses")

class Announcement(Base):
    __tablename__ = "announcements"
    id = Column(Integer, primary_key=True)
    creator_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(String, default=datetime.now(timezone.utc).isoformat())
    title = Column(String, nullable=False)
    content = Column(String, nullable=False)  # Changed from JSONB to String
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

    user = relationship("User", back_populates="form_responses")
    form = relationship("Form", back_populates="responses")


class Gradeable(Base):
    __tablename__ = "gradeables"
    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    #description = Column(String, nullable=True)
    #due_date = Column(String, nullable=False)
    max_points = Column(Integer, nullable=False)
    creator_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(String, default=datetime.now(timezone.utc).isoformat())

    creator = relationship("User", back_populates="gradeables")
    scores = relationship("GradeableScores", back_populates="gradeable")

    @validates("creator_id")
    def validate_creator(self, key, value):
        with SessionLocal() as session:
            user = session.query(User).filter_by(id=value).first()
            if user and user.role == RoleType.STUDENT:
                raise ValueError("Students cannot create gradeables.")
            return value
    
class GradeableScores(Base):
    __tablename__ = "gradeable_scores"
    id = Column(Integer, primary_key=True)
    gradeable_id = Column(Integer, ForeignKey("gradeables.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    score = Column(Integer, nullable=False)
    #feedback = Column(String, nullable=True)

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
        with SessionLocal() as session:
            user = session.query(User).filter_by(id=value).first()
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
        with SessionLocal() as session:
            user = session.query(User).filter_by(id=value).first()
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
    
# First, add these models after your existing models

class FeedbackSubmission(Base):
    __tablename__ = "feedback_submissions"
    id = Column(Integer, primary_key=True)
    submitter_id = Column(Integer, ForeignKey("users.id"))
    team_id = Column(Integer, ForeignKey("teams.id"))
    submitted_at = Column(DateTime, default=datetime.now(timezone.utc))
    submitter = relationship("User", foreign_keys=[submitter_id])
    team = relationship("Team")
    details = relationship("FeedbackDetail", back_populates="submission")

class FeedbackDetail(Base):
    __tablename__ = "feedback_details"
    id = Column(Integer, primary_key=True)
    submission_id = Column(Integer, ForeignKey("feedback_submissions.id"))
    member_id = Column(Integer, ForeignKey("users.id"))
    contribution = Column(Float)
    remarks = Column(Text)
    submission = relationship("FeedbackSubmission", back_populates="details")
    member = relationship("User", foreign_keys=[member_id])

# Add these Pydantic models for request validation
class FeedbackDetailRequest(BaseModel):
    member_id: int
    contribution: float
    remarks: str

class FeedbackSubmissionRequest(BaseModel):
    team_id: int
    details: List[FeedbackDetailRequest]

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
    title: str = FastAPIForm(...)
    # max_points: str = FastAPIForm(...)
    
    # @validator('due_date')
    # def validate_due_date(cls, v):
    #     try:
    #         # Validate ISO 8601 format
    #         datetime.fromisoformat(v.replace('Z', '+00:00'))
    #         return v
    #     except ValueError:
    #         raise ValueError("Invalid due date format. Use ISO 8601 (YYYY-MM-DDTHH:MM:SSZ)")
            
    # @validator('max_points')
    # def validate_max_points(cls, v):
    #     if v <= 0:
    #         raise ValueError("Maximum points must be greater than zero")
    #     return v

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
dotenv.load_dotenv()
SECRET_KEY = os.getenv("SECRET_KEY")
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
    print("I received token:", token)
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
# def login(request: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == request.username).first()
    
    # Verify credentials
    if not user or not verify_password(request.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    # Get the role
    role = db.query(Role).filter(Role.id == user.role_id).first().role
    
    # Generate token
    token = generate_token({"sub": user.username}, timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    
    return {"access_token": token, "token_type": "bearer", "role": role}

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

def extract_students(content: str) -> List[dict]:
    """
    Extracts student data from the CSV content.
    Returns a list of dictionaries with student data.
    """
    reader = csv.DictReader(content.splitlines())
    students = []
    expected_headers = ['RollNo','Name', 'Email']
    headers = reader.fieldnames

    for header in expected_headers:
        if header not in headers:
            raise CSVFormatError(f"Missing header: {header}")
    
    for row in reader:
        student = {
            'RollNo': row.get('RollNo'),
            'Name': row.get('Name'),
            'Email': row.get('Email'),
            
        }
        students.append(student)
    

    for student in students:
        if not student['RollNo'] or not student['Name'] or not student['Email']:
            print(student)
            raise CSVFormatError("All fields must be filled for each student.")
    
    return students

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
        content_str = content.decode('utf-8')
        
        try:
            students = extract_students(content_str)
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
                # extract username from email
                username = student['Email'].split('@')[0]
                # Check if username already exists
                existing_user = db.query(User).filter(User.username == username).first()
                if existing_user:
                    errors.append(f"Username {username} already exists")
                    continue
                
                # Generate random password
                temp_password = generate_random_string(10)
                hashed_password = create_hashed_password(temp_password)
                
                # Create new student
                if 'RollNo' in student:
                    user_id = student['RollNo']
                else:
                    user_id = None
                new_student = User(
                    id=user_id,
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
    content: str
    url_name: Optional[str] = None

    class Config:
        orm_mode = True

@app.post('/announcements', status_code=status.HTTP_201_CREATED)
async def create(
    title: str = FastAPIForm(...),
    description: str = FastAPIForm(...),
    file: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    saved_file_path = None
    try:
        # Create file path and url_name
        url_name = None
        if file:
            # Create file path
            file_extension = os.path.splitext(file.filename)[1]
            file_name = f"{uuid.uuid4()}{file_extension}"
            saved_file_path = os.path.join("uploads", file_name)
            
            # Ensure uploads directory exists
            os.makedirs("uploads", exist_ok=True)
            
            # Save the file
            with open(saved_file_path, "wb") as buffer:
                content = await file.read()
                buffer.write(content)
            
            url_name = file_name
        
        # Create announcement in database
        db_announcement = Announcement(
            title=title,
            content=description,
            url_name=url_name,
            creator_id=1  # Default creator ID
        )
        db.add(db_announcement)
        db.commit()
        db.refresh(db_announcement)
        
        return db_announcement
    except Exception as e:
        db.rollback()
        # Only delete the file if database operation failed
        if saved_file_path and os.path.exists(saved_file_path):
            try:
                os.remove(saved_file_path)
            except OSError:
                pass  # Ignore file deletion errors during cleanup
        raise HTTPException(status_code=500, detail=str(e))

@app.get('/announcements/{id}/download')
async def download_announcement_file(
    id: int,
    db: Session = Depends(get_db)
):
    try:
        announcement = db.query(Announcement).filter(Announcement.id == id).first()
        if not announcement or not announcement.url_name:
            raise HTTPException(status_code=404, detail="File not found")
        
        file_path = os.path.join("uploads", announcement.url_name)
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="File not found")
        
        return FileResponse(
            file_path,
            filename=announcement.url_name,
            media_type='application/octet-stream'
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get('/announcements', response_model=List[Show])
def all(db: Session = Depends(get_db)):
    try:
        announcements = db.query(Announcement).order_by(Announcement.created_at.desc()).all()
        return announcements
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get('/announcements/{id}', status_code=200, response_model=Show)
def show(id: int, db: Session = Depends(get_db)):
    try:
        announcement = db.query(Announcement).filter(Announcement.id == id).first()
        if not announcement:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f'Announcement with id {id} not found')
        return announcement
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete('/announcements/{id}', status_code=status.HTTP_204_NO_CONTENT)
def destroy(id: int, db: Session = Depends(get_db)):
    try:
        announcement = db.query(Announcement).filter(Announcement.id == id).first()
        if not announcement:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f'Announcement with id: {id} not found')
        
        # Delete the associated file if it exists
        if announcement.url_name:
            file_path = os.path.join("uploads", announcement.url_name)
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except OSError as e:
                    print(f"Error deleting file: {e}")  # Log error but continue with announcement deletion
        
        # Delete the announcement from database
        db.delete(announcement)
        db.commit()
        
        return {'message': 'Announcement deleted successfully'}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error deleting announcement: {str(e)}")

@app.put('/announcements/{id}', status_code=status.HTTP_202_ACCEPTED)
async def update(
    id: int,
    title: str = FastAPIForm(...),
    description: str = FastAPIForm(...),
    file: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    try:
        # Find the announcement
        announcement = db.query(Announcement).filter(Announcement.id == id).first()
        if not announcement:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f'Announcement with id: {id} not found'
            )
        
        # Keep track of the old file path if it exists
        old_file_path = None
        if announcement.url_name:
            old_file_path = os.path.join("uploads", announcement.url_name)
        
        # Handle file upload if provided
        if file:
            # Create new file path
            file_extension = os.path.splitext(file.filename)[1]
            new_file_name = f"{uuid.uuid4()}{file_extension}"
            new_file_path = os.path.join("uploads", new_file_name)
            
            # Ensure uploads directory exists
            os.makedirs("uploads", exist_ok=True)
            
            # Save the new file
            try:
                contents = await file.read()
                with open(new_file_path, "wb") as f:
                    f.write(contents)
                
                # Update announcement with new file info
                announcement.url_name = new_file_name
                
                # Delete old file if it exists
                if old_file_path and os.path.exists(old_file_path):
                    try:
                        os.remove(old_file_path)
                    except OSError:
                        print(f"Warning: Could not delete old file: {old_file_path}")
            except Exception as e:
                # If anything goes wrong with file handling, clean up
                if os.path.exists(new_file_path):
                    os.remove(new_file_path)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Error handling file upload: {str(e)}"
                )
        
        # Update announcement fields
        announcement.title = title
        announcement.content = description
        
        # Commit changes
        db.commit()
        db.refresh(announcement)
        
        # Return updated announcement
        return {
            "id": announcement.id,
            "title": announcement.title,
            "content": announcement.content,
            "url_name": announcement.url_name,
            "created_at": announcement.created_at,
            "creator_id": announcement.creator_id
        }
        
    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating announcement: {str(e)}"
        )

@app.delete('/announcements/{id}', status_code=status.HTTP_204_NO_CONTENT)
def destroy(id: int, db: Session = Depends(get_db)):
    try:
        announcement = db.query(Announcement).filter(Announcement.id == id).first()
        if not announcement:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f'Announcement with id: {id} not found')
        
        # Delete the associated file if it exists
        if announcement.url_name:
            file_path = os.path.join("uploads", announcement.url_name)
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except OSError as e:
                    print(f"Error deleting file: {e}")  # Log error but continue with announcement deletion
        
        # Delete the announcement from database
        db.delete(announcement)
        db.commit()
        
        return {'message': 'Announcement deleted successfully'}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error deleting announcement: {str(e)}")


@app.post("/quiz/create")
def create_quiz():
    pass

@app.get("/forms/")
def get_forms():
    pass

@app.post("/forms/create")
def create_form():
    pass


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
def get_people(
    token: str = Depends(prof_or_ta_required),
    db: Session = Depends(get_db)
    ):
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


@app.get("/people/csv")
async def get_people(
    token: str = Depends(prof_or_ta_required),
    db: Session = Depends(get_db)
    ):
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
    # Convert to CSV
    csv_data = "id,name,email,role\n"
    for user in return_data:
        csv_data += f"{user['id']},{user['name']},{user['email']},{user['role']}\n"
    # Create a response with the CSV data
    response = Response(content=csv_data, media_type="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=people.csv"
    return response
    
    # return FileResponse()



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

def store_form_response_db(response_data: FormResponseSubmit, 
                            user_id: int,  # Current user information
                           db: Session = Depends(get_db)):
    """
    Store a user's response to a form
    
    Parameters:
    - response_data: FormResponseSubmit object
    - user_id: Current user information
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
            FormResponse.user_id == user_id
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
                user_id=user_id,
                response_data=response_data.response_data,
                submitted_at=datetime.now(timezone.utc).isoformat()
            )
            db.add(new_response)
            message = "Response submitted successfully"
        
        db.commit()
        
        return {
            "message": message,
            "form_id": response_data.form_id,
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
async def api_create_form(form_data: FormCreateRequest, token: str = Depends(prof_or_ta_required), db: Session = Depends(get_db)):
    """Create a new form"""
    result = create_form_db(form_data, db)
    return JSONResponse(status_code=201, content=result)

@app.post("/api/forms/submit")
async def api_submit_response(form_response: FormResponseSubmit, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Submit a response to a form"""
    result = store_form_response_db(form_response, user["user"].id, db)
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
async def api_get_forms(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Get all forms with info about whether the user has submitted a response"""
    print("over here")
    forms = get_all_forms_db(user["user"].id, db)
    print("Forms:", forms)
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



@app.get("/gradeables/")
async def get_gradeable_table(
    db: Session = Depends(get_db),
    token: str = Depends(prof_or_ta_required)
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
            "max_points": gradeable.max_points,
            "creator_id": gradeable.creator_id,
        })
    return JSONResponse(status_code=200, content=results)

@app.get("/gradeables/{gradeable_id}")
async def get_gradeable_by_id(
    gradeable_id: int,
    db: Session = Depends(get_db),
    token: str = Depends(prof_or_ta_required)
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

def parse_scores_from_csv(csv_content: str, gradeable_id: int, max_points: int, db: Session) -> List[Dict[str, Any]]:
    """
    Parse CSV content containing user scores.
    Expected CSV format: username,score
    First row should be headers.
    
    Parameters:
    - csv_content: CSV file content as string
    - gradeable_id: ID of the gradeable
    - max_points: Maximum points possible
    - db: Database session
    
    Returns:
        List of dictionaries with user_id, gradeable_id and score
    """
    scores = []
    processed_user_ids = set()
    
    try:
        csv_file = StringIO(csv_content)
        csv_reader = csv.DictReader(csv_file)
        
        # Verify required headers
        # required_headers = {'username', 'score'}
        # if not all(header in csv_reader.fieldnames for header in required_headers):
        #     raise ValueError(f"CSV must contain headers: {', '.join(required_headers)}")
        
        # Process each row in CSV
        for row_num, row in enumerate(csv_reader, start=2):
            try:
                # Extract and validate username
                username = row['username'].strip()
                if not username:
                    continue
                
                # Extract and validate score
                try:
                    score = int(row['score'])
                    if score < 0 or score > max_points:
                        raise ValueError(f"Score must be between 0 and {max_points}")
                except ValueError:
                    raise ValueError(f"Invalid score format in row {row_num}")
                
                # Get user ID from username
                user = db.query(User).filter(User.username == username).first()
                if not user:
                    raise ValueError(f"User with username '{username}' not found")
                print(user.id)
                scores.append({
                    'user_id': user.id,
                    'gradeable_id': gradeable_id,
                    'score': score
                })
                processed_user_ids.add(user.id)
                
            except ValueError as e:
                print(f"Warning: Skipping row {row_num}: {str(e)}")
                continue
        
        # Get student role ID
        student_role = db.query(Role).filter(Role.role == RoleType.STUDENT).first()
        if not student_role:
            raise ValueError("Student role not found in database")
        
        # Add default score of 0 for students not in CSV
        students = db.query(User).filter(User.role_id == student_role.id).all()
        for student in students:
            if student.id not in processed_user_ids:
                scores.append({
                    'user_id': student.id,
                    'gradeable_id': gradeable_id,
                    'score': 0
                })
        
        return scores
        
    except csv.Error as e:
        raise ValueError(f"Error parsing CSV file: {str(e)}")
    except Exception as e:
        raise ValueError(f"Unexpected error processing CSV: {str(e)}")
@app.get("/gradeables/{gradeable_id}/scores")
async def get_gradeable_submissions(
    gradeable_id: int,
    db: Session = Depends(get_db),
    token: str = Depends(prof_or_ta_required)
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
            "gradeable_id": submission.gradeable_id,
            "submitted_at": submission.submitted_at,
            "score": submission.score
        })
    return JSONResponse(status_code=200, content=results)

# @app.post("/gradeables/create")
# async def create_gradeable(
#     gradeable: GradeableCreateRequest,
#     file: UploadFile = File(...),
# )

# @app.post("/gradeables/{gradeable_id}/upload-scores")
# async def upload_gradeable_scores(
#     gradeable_id: int,
#     file: UploadFile = File(...),
#     db: Session = Depends(get_db),
#     token: str = Depends(prof_or_ta_required)
# ):
#     """
#     Upload scores for a specific gradeable
#     """
#     # Ensure the file is a CSV
#     if not file.filename.endswith('.csv'):
#         raise HTTPException(
#             status_code=status.HTTP_400_BAD_REQUEST,
#             detail="Only CSV files are allowed"
#         )
    
#     try:
#         # Validate gradeable exists and get max points
#         gradeable = db.query(Gradeable).filter(Gradeable.id == gradeable_id).first()
#         if not gradeable:
#             raise HTTPException(
#                 status_code=status.HTTP_404_NOT_FOUND,
#                 detail="Gradeable not found"
#             )
        
#         # Read and parse file content
#         content = await file.read()
#         content_str = content.decode('utf-8')
        
#         # Parse scores with detailed validation
#         scores = parse_scores_from_csv(
#             csv_content=content_str, 
#             gradeable_id=gradeable_id, 
#             max_points=gradeable.max_points,
#             db=db
#         )
        
#         # Bulk upsert scores
#         for score_data in scores:
#             existing_submission = db.query(GradeableScores).filter(
#                 GradeableScores.gradeable_id == gradeable_id,
#                 GradeableScores.user_id == score_data["user_id"]
#             ).first()
            
#             if existing_submission:
#                 existing_submission.score = score_data["score"]
#             else:
#                 new_submission = GradeableScores(
#                     user_id=score_data["user_id"],
#                     gradeable_id=gradeable_id,
#                     score=score_data["score"]
#                 )
#                 db.add(new_submission)
        
#         db.commit()
        
#         return JSONResponse(status_code=200, content={
#             "message": "Scores uploaded successfully",
#             "gradeable_id": gradeable_id,
#             "total_submissions": len(scores)
#         })
    
#     except ValueError as ve:
#         db.rollback()
#         raise HTTPException(status_code=400, detail=str(ve))
#     except Exception as e:
#         db.rollback()
#         raise HTTPException(status_code=500, detail=f"Unexpected error uploading scores: {str(e)}")
        
        

@app.post("/gradeables/create")
async def create_gradeable(
    # gradeable: GradeableCreateRequest,
    title: str = FastAPIForm(...),
    max_points: str = FastAPIForm(...),
    file: UploadFile = File(...), # CSV file,
    user_data: User = Depends(prof_or_ta_required),
    db: Session = Depends(get_db)
):
    """Create a new gradeable"""
    username = user_data.get('sub')
    user = db.query(User).filter(User.username == username).first()
    print("2137")
    try:
        print("Title is", title, "Max points is", max_points, "Creator ID is", user.id)
        new_gradeable = Gradeable(
            title=title,
            max_points=int(max_points),
            creator_id=user.id
        )
        
        print("Hello")
        db.add(new_gradeable)
        db.commit()
        db.refresh(new_gradeable)
        print(new_gradeable.id)
        print("HELLO")

        # Read and parse file content
        content = await file.read()
        content_str = content.decode('utf-8')
        scores = parse_scores_from_csv(
            csv_content=content_str, 
            gradeable_id=new_gradeable.id, 
            max_points=new_gradeable.max_points,
            db=db
        )
        gradeable_id = new_gradeable.id
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
        
        return JSONResponse(status_code=201, content={
            "id": new_gradeable.id,
            "title": new_gradeable.title,
            "max_points": int(new_gradeable.max_points),
            "creator_id": new_gradeable.creator_id,
        })
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error creating gradeable: {str(e)}"
        )


# def parse_scores_from_csv(csv_content: str, 
#     gradeable_id: int, 
#     max_points: int,
#     db: Session) -> List[Dict[str, Any]]:
#     """
#     Parse CSV content containing user scores.
#     Expected CSV format: user_id,score
#     First row should be headers.
    
#     Also assigns a default score of 0 to any student who doesn't have a score in the CSV.
    
#     Returns:
#         List of dictionaries with user_id and score
#     """
#     # import csv
#     # from io import StringIO
    
#     scores = []
#     processed_usernames = set()
    
#     # Parse the CSV content
#     try:
#         csv_file = StringIO(csv_content)
#         csv_reader = csv.DictReader(csv_file)
        
#         # Check required headers
#         required_headers = ['id','username', 'score']
#         headers = csv_reader.fieldnames
#         print("headers are", headers)
#         # if not all(header in headers for header in required_headers):
#         #     print(f"Warning: Extra headers found: {headers}. Proceeding with parsing.")
#         #     raise ValueError(f"CSV must contain headers: {', '.join(required_headers)}")
#         print("line")
#         # Process each row
#         for row_num, row in enumerate(csv_reader, start=2):
#             print("hihfi")
#             print("Row is", row)
#             try:
#                 username = row['username'].strip()
#                 score = int(row['score'])
                
#                 user = db.query(User).filter(User.username == username).first()
#                 if not user:
#                     raise ValueError(f"User with username '{username}' not found on row {row_num}")

#                 print("User ID is", user_id, "Score is", score)
#                 scores.append({
#                     'user_id': user_id,
#                     'score': score
#                 })
#                 processed_usernames.add(username)
#             except (ValueError, KeyError) as e:
#                 # Skip invalid rows but continue processing
#                 print(f"Error processing row: {row}. Error: {str(e)}")
#                 continue
    
#     except Exception as e:
#         raise ValueError(f"Error parsing CSV: {str(e)}")
    
#     # Get all students from the database and add default score of 0 for missing ones
#         # Get student role ID
#     student_role = db.query(Role).filter(Role.role == RoleType.STUDENT).first()
#     if student_role:
#         students = db.query(User).filter(User.role_id == student_role.id).all()
        
#         for student in students:
#             if student.id not in processed_user_ids:
#                 scores.append({
#                     'user_id': student.id,
#                     'score': 0
#                 })
    
#     return scores

@app.get("/gradeables/{gradeable_id}/upload-scores")
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
        # Read file content
        content = await file.read()
        content_str = content.decode('utf-8')
        
        # Parse CSV content
        scores = parse_scores_from_csv(content_str)
        
        # Update scores in the database
        for score in scores:
            submission = db.query(GradeableScores).filter(
                GradeableScores.gradeable_id == gradeable_id,
                GradeableScores.user_id == score["user_id"]
            ).first()
            
            if submission:
                submission.score = score["score"]
                submission.submitted_at = datetime.now(timezone.utc).isoformat()
            else:
                new_submission = GradeableScores(
                    user_id=score["user_id"],
                    gradeable_id=gradeable_id,
                    score=score["score"],
                    submitted_at=datetime.now(timezone.utc).isoformat()
                )
                db.add(new_submission)
        
        db.commit()
        
        return JSONResponse(status_code=200, content={
            "message": "Scores uploaded successfully",
            "gradeable_id": gradeable_id,
            "total_submissions": len(scores)
        })
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error uploading scores: {str(e)}")


@app.post("/submittables/{submittable_id}/submit")
async def submit_file(
    submittable_id: int,
    files: List[UploadFile] = File(...),  # Now accepts multiple files
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Submit multiple files for a submittable"""
    try:
        # Get the submittable
        submittable = db.query(Submittable).filter(Submittable.id == submittable_id).first()
        if not submittable:
            raise HTTPException(status_code=404, detail="Submittable not found")
        
        # Check if submission is still open
        now = datetime.now(timezone.utc)
        deadline = datetime.fromisoformat(submittable.deadline.replace('Z', '+00:00'))
        if now > deadline:
            raise HTTPException(status_code=400, detail="Submission deadline has passed")
        
        # Get user's team
        user = current_user["user"]
        team = db.query(Team).filter(Team.id == user.team_id).first()
        if not team:
            raise HTTPException(status_code=400, detail="User is not part of a team")
        
        # Create submission record
        new_submission = Submission(
            team_id=team.id,
            submittable_id=submittable_id
        )
        db.add(new_submission)
        db.commit()
        db.refresh(new_submission)
        
        # Save all submitted files
        for file in files:
            file_extension = file.filename.split('.')[-1]
            file_name = f"submission_{uuid.uuid4()}.{file_extension}"
            file_path = f"uploads/{file_name}"
            
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            
            new_file = SubmissionFile(
                submission_id=new_submission.id,
                file_url=f"/uploads/{file_name}",  # URL path
                original_filename=file.filename
            )
            db.add(new_file)
        
        db.commit()
        
        return JSONResponse(status_code=201, content={
            "message": "Files submitted successfully",
            "submission_id": new_submission.id
        })
    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error submitting files: {str(e)}")

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
        
        # Return list of files in the submission
        files = []
        for file in submission.files:
            local_path = file.file_url.lstrip('/')
            if not os.path.exists(local_path):
                continue
            files.append({
                "id": file.id,
                "original_filename": file.original_filename,
                "file_url": file.file_url
            })
        
        return JSONResponse(status_code=200, content={
            "submission_id": submission_id,
            "submitted_on": submission.submitted_on,
            "files": files
        })
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error downloading submission: {str(e)}")

@app.get("/submissions/{submission_id}/files/{file_id}/download")
async def download_submission_file(
    submission_id: int,
    file_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Download a specific file from a submission"""
    try:
        submission = db.query(Submission).filter(Submission.id == submission_id).first()
        if not submission:
            raise HTTPException(status_code=404, detail="Submission not found")
        
        file = db.query(SubmissionFile).filter(
            SubmissionFile.id == file_id,
            SubmissionFile.submission_id == submission_id
        ).first()
        
        if not file:
            raise HTTPException(status_code=404, detail="File not found")
        
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
        
        # Convert URL path to local path
        local_path = file.file_url.lstrip('/')
        if not os.path.exists(local_path):
            raise HTTPException(status_code=404, detail="File not found")
        
        return FileResponse(
            local_path,
            filename=file.original_filename,
            media_type="application/octet-stream"
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error downloading file: {str(e)}")

@app.get("/submittables/")
async def get_submittables(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get all submittables with their status (upcoming, open, closed) and submission status for students"""
    try:
        submittables = db.query(Submittable).all()
        now = datetime.now(timezone.utc)
        user = current_user["user"]
        role = current_user["role"]
        
        result = {
            "upcoming": [],
            "open": [],
            "closed": []
        }
        
        for submittable in submittables:
            opens_at = datetime.fromisoformat(submittable.opens_at.replace('Z', '+00:00')) if submittable.opens_at else None
            deadline = datetime.fromisoformat(submittable.deadline.replace('Z', '+00:00'))
            
            submittable_data = {
                "id": submittable.id,
                "description": submittable.description,
                "deadline": submittable.deadline,
                "reference_files": [
                    {
                        "id": ref.id,
                        "original_filename": ref.original_filename
                    } for ref in submittable.reference_files
                ]
            }
            
            # Add submission status for students
            if role == RoleType.STUDENT and user.team_id:
                submission = db.query(Submission).filter(
                    Submission.submittable_id == submittable.id,
                    Submission.team_id == user.team_id
                ).first()
                
                if submission:
                    submittable_data["submission_status"] = {
                        "has_submitted": True,
                        "submission_id": submission.id,
                        "submitted_on": submission.submitted_on,
                        "original_filename": submission.original_filename
                    }
                else:
                    submittable_data["submission_status"] = {
                        "has_submitted": False,
                        "submission_id": None,
                        "submitted_on": None,
                        "original_filename": None
                    }
            
            if opens_at and now < opens_at:
                result["upcoming"].append(submittable_data)
            elif now <= deadline:
                result["open"].append(submittable_data)
            else:
                result["closed"].append(submittable_data)
        
        return JSONResponse(status_code=200, content=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching submittables: {str(e)}")

@app.get("/submittables/{submittable_id}/reference-files/{ref_file_id}/download")
async def download_reference_file(
    submittable_id: int,
    ref_file_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Download a reference file"""
    try:
        ref_file = db.query(SubmittableReferenceFile).filter(
            SubmittableReferenceFile.id == ref_file_id,
            SubmittableReferenceFile.submittable_id == submittable_id
        ).first()
        
        if not ref_file:
            raise HTTPException(status_code=404, detail="Reference file not found")
        
        # Convert URL path to local path
        local_path = ref_file.file_url.lstrip('/')
        if not os.path.exists(local_path):
            raise HTTPException(status_code=404, detail="Reference file not found")
        
        return FileResponse(
            local_path,
            filename=ref_file.original_filename,
            media_type="application/octet-stream"
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error downloading reference file: {str(e)}")


@app.post("/submittables/create")
async def create_submittable(
    title: str = FastAPIForm(...),
    deadline: str = FastAPIForm(...),
    description: str = FastAPIForm(...),
    opens_at: Optional[str] = FastAPIForm(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    token: str = Depends(prof_required)
):
    """Create a new submittable with reference files"""
    try:
        # Basic validation
        try:
            datetime.fromisoformat(deadline.replace('Z', '+00:00'))
            if opens_at:
                datetime.fromisoformat(opens_at.replace('Z', '+00:00'))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format")
        
        # Get the creator (professor) from token
        # Fix: Don't decode the token as it's already decoded by the dependency
        # payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        payload = token  # The token is already decoded by prof_required dependency
        username = payload.get("sub")
        user = db.query(User).filter(User.username == username).first()
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Save the reference file
        file_extension = file.filename.split('.')[-1]
        file_name = f"ref_{uuid.uuid4()}.{file_extension}"
        file_path = f"uploads/{file_name}"
        
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Create submittable in database with file information
        new_submittable = Submittable(
            title=title,
            opens_at=opens_at,
            deadline=deadline,
            description=description,
            creator_id=user.id,
            file_url=f"uploads/{file_name}",  # URL path without leading slash
            original_filename=file.filename
        )
        
        db.commit()
        
        return JSONResponse(status_code=201, content={
            "message": "Submittable created successfully",
            "submittable_id": new_submittable.id
        })
    except HTTPException as he:
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)  # Clean up file if validation fails
        raise he
    except Exception as e:
        db.rollback()
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)  # Clean up file if something went wrong
        raise HTTPException(status_code=500, detail=f"Error creating submittable: {str(e)}")

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
            "opens_at": submittable.opens_at,
            "deadline": submittable.deadline,
            "description": submittable.description,
            "created_at": submittable.created_at,
            "reference_files": [
                {
                    "id": ref.id,
                    "original_filename": ref.original_filename
                } for ref in submittable.reference_files
            ]
        })
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching submittable: {str(e)}")

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
                "files": [
                    {
                        "id": file.id,
                        "original_filename": file.original_filename
                    } for file in submission.files
                ]
            }
            result.append(submission_data)
        
        return JSONResponse(status_code=200, content=result)
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching submissions: {str(e)}")

@app.delete("/submittables/{submittable_id}")
async def delete_submittable(
    submittable_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Delete a submittable (professors only)"""
    try:
        if current_user["role"] != RoleType.PROF:
            raise HTTPException(status_code=403, detail="Only professors can delete submittables")
        
        submittable = db.query(Submittable).filter(Submittable.id == submittable_id).first()
        if not submittable:
            raise HTTPException(status_code=404, detail="Submittable not found")
        
        # Delete associated files
        for ref_file in submittable.reference_files:
            local_path = ref_file.file_url.lstrip('/')
            if os.path.exists(local_path):
                os.remove(local_path)
        
        # Delete from database
        db.delete(submittable)
        db.commit()
        
        return JSONResponse(status_code=200, content={"message": "Submittable deleted successfully"})
    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error deleting submittable: {str(e)}")


@app.put("/submittables/{submittable_id}")
async def update_submittable(
    submittable_id: int,
    title: str = FastAPIForm(...),
    deadline: str = FastAPIForm(...),
    description: str = FastAPIForm(...),
    opens_at: Optional[str] = FastAPIForm(None),
    file: Optional[UploadFile] = None,
    db: Session = Depends(get_db),
    token: str = Depends(prof_required)
):
    """Update a submittable (professors only)"""
    try:
        # Basic validation
        try:
            datetime.fromisoformat(deadline.replace('Z', '+00:00'))
            if opens_at:
                datetime.fromisoformat(opens_at.replace('Z', '+00:00'))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format")
            
        existing_submittable = db.query(Submittable).filter(Submittable.id == submittable_id).first()
        if not existing_submittable:
            raise HTTPException(status_code=404, detail="Submittable not found")
        
        # Update basic information
        existing_submittable.title = title
        existing_submittable.opens_at = opens_at
        existing_submittable.deadline = deadline
        existing_submittable.description = description
        
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
            
            existing_submittable.file_url = f"uploads/{file_name}"
            existing_submittable.original_filename = file.filename
        
        db.commit()
        db.refresh(existing_submittable)
        
        return JSONResponse(status_code=200, content={
            "message": "Submittable deleted successfully",
            "submittable_id": submittable_id
        })
    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)  # Clean up file if something went wrong
        raise HTTPException(status_code=500, detail=f"Error updating submittable: {str(e)}")

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
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/feedback/students")
async def get_student_feedback_info(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get student's team and member data with feedback submission validation"""
    try:
        user = current_user["user"]
        
        # Check if user is a student
        if current_user["role"] != RoleType.STUDENT:
            raise HTTPException(
                status_code=403,
                detail="Only students can access this endpoint"
            )

        # Check if user has been assigned to a team
        if not user.teams:
            raise HTTPException(
                status_code=404,
                detail="You have not been assigned to a team"
            )
            
        team = user.teams[0]  # Get the student's team

        # Get all team members including the current user
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

        # Check if user has already submitted feedback
        existing_submission = db.query(FeedbackSubmission).filter(
            FeedbackSubmission.submitter_id == user.id,
            FeedbackSubmission.team_id == team.id
        ).first()

        # If there's an existing submission, include the feedback details
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

@app.post("/feedback/student/submit")
async def submit_student_feedback(
    feedback: FeedbackSubmissionRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Submit feedback for team members"""
    try:
        user = current_user["user"]
        
        # Check if user is a student
        if current_user["role"] != RoleType.STUDENT:
            raise HTTPException(
                status_code=403,
                detail="Only students can submit feedback"
            )

        # Check if user belongs to the team they're submitting feedback for
        if not any(team.id == feedback.team_id for team in user.teams):
            raise HTTPException(
                status_code=403,
                detail="You can only submit feedback for your own team"
            )

        # Check if user has already submitted feedback
        existing_submission = db.query(FeedbackSubmission).filter(
            FeedbackSubmission.submitter_id == user.id,
            FeedbackSubmission.team_id == feedback.team_id
        ).first()

        if existing_submission:
            raise HTTPException(
                status_code=400,
                detail="You have already submitted feedback for this team"
            )

        # Validate that all team members are being rated (except the submitter)
        team = next(team for team in user.teams if team.id == feedback.team_id)
        expected_member_count = len(team.members)  # Exclude the submitter
        if len(feedback.details) != expected_member_count:
            raise HTTPException(
                status_code=400,
                detail="Feedback must be provided for all team members"
            )

        # Validate that the rated members are actually in the team
        team_member_ids = {member.id for member in team.members}
        submitted_member_ids = {detail.member_id for detail in feedback.details}
        if team_member_ids != submitted_member_ids:
            raise HTTPException(
                status_code=400,
                detail="Feedback can only be provided for current team members"
            )

        # Validate total contribution equals 100%
        total_contribution = sum(detail.contribution for detail in feedback.details)
        if total_contribution != 100:
            raise HTTPException(
                status_code=400,
                detail="Total contribution must equal 100%"
            )

        # Create feedback submission
        new_submission = FeedbackSubmission(
            submitter_id=user.id,
            team_id=feedback.team_id,
            submitted_at=datetime.now(timezone.utc)
        )
        db.add(new_submission)
        db.flush()  # Get the ID before committing

        # Create feedback details
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

@app.get("/feedback/admin")
async def get_admin_feedback(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all teams that have at least one feedback submission"""
    try:
        # Check if user is an admin (TA or professor)
        if current_user["role"] not in [RoleType.TA, RoleType.PROF]:
            raise HTTPException(
                status_code=403,
                detail="Only teaching assistants and professors can access this endpoint"
            )

        # Get all teams that have feedback submissions
        teams_with_feedback = (
            db.query(Team)
            .join(FeedbackSubmission, Team.id == FeedbackSubmission.team_id)
            .distinct()
            .all()
        )

        result = []
        for team in teams_with_feedback:
            # Get submission count for this team
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

@app.get("/feedback/admin/view/{team_id}")
async def get_team_feedback_details(
    team_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get detailed feedback submissions for a specific team"""
    try:
        # Check if user is an admin (TA or professor)
        if current_user["role"] not in [RoleType.TA, RoleType.PROF]:
            raise HTTPException(
                status_code=403,
                detail="Only teaching assistants and professors can access this endpoint"
            )

        # Check if team exists
        team = db.query(Team).filter(Team.id == team_id).first()
        if not team:
            raise HTTPException(status_code=404, detail="Team not found")

        # Get all feedback submissions for this team
        submissions = (
            db.query(FeedbackSubmission)
            .filter(FeedbackSubmission.team_id == team_id)
            .all()
        )

        # Get all team members for reference
        team_members = {
            member.id: member.name 
            for member in team.members
        }

        # Format the submissions with detailed information
        formatted_submissions = []
        for submission in submissions:
            # Get details for this submission
            feedback_details = (
                db.query(FeedbackDetail)
                .filter(FeedbackDetail.submission_id == submission.id)
                .all()
            )

            # Get submitter info
            submitter = db.query(User).filter(User.id == submission.submitter_id).first()

            formatted_submissions.append({
                "submission_id": submission.id,
                "submitter": {
                    "id": submitter.id,
                    "name": submitter.name
                },
                "submitted_at": submission.submitted_at.isoformat(),
                "feedback": [
                    {
                        "member_id": detail.member_id,
                        "member_name": team_members.get(detail.member_id, "Unknown"),
                        "contribution": detail.contribution,
                        "remarks": detail.remarks
                    }
                    for detail in feedback_details
                ]
            })

        return {
            "team_id": team.id,
            "team_name": team.name,
            "members": team_members,
            "submissions": formatted_submissions
        }

    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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

@app.websocket("/discussions/ws/{channel_id}")
async def websocket_endpoint(
    websocket: WebSocket, 
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

    await manager.connect(websocket, channel_id, user["id"])
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


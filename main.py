import json
from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, Query, Header, Body, File
from fastapi.responses import JSONResponse, Response
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy import ForeignKey, create_engine, Column, Integer, String, Enum, Table
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
from fastapi.staticfiles import StaticFiles

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
    content = Column(JSONB, nullable=False)
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

    @validates("creator_id")
    def validate_creator(self, key, value):
        user = SessionLocal.query(User).filter_by(id=value).first()
        if user and user.role == RoleType.STUDENT:
            raise ValueError("Students cannot create gradeables.")
        return value

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

SECRET_KEY = secrets.token_hex(32)
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
                    "name": new_t_ta.name,
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
    content: dict
    url_name: Optional[str] = None

    class Config:
        orm_mode = True

@app.post('/announcements', status_code=status.HTTP_201_CREATED)
async def create(
    title: Annotated[str, Form()],
    description: Annotated[str, Form()],
    file: UploadFile | None = None,
    db: Session = Depends(get_db),
    #current_user: dict = Depends(get_current_user)
):
    file_location = None
    if file:
        file_extension = file.filename.split('.')[-1]
        file_name = f"{uuid.uuid4()}.{file_extension}"
        file_location = f"uploads/{file_name}"
        with open(file_location, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

    try:
        description_json = json.loads(description)
    except json.JSONDecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON for description")
    
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    new_announcement = Announcement(
        creator_id=1,
        created_at=current_time,
        title=title,
        content=description_json,
        url_name=file_location if file_location else None
    )
    db.add(new_announcement)
    db.commit()
    db.refresh(new_announcement)
    return new_announcement


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

@app.put('/announcements/{id}', status_code=status.HTTP_202_ACCEPTED)
def update(
    id: int,
    title: Annotated[str, Form()],
    description: Annotated[str, Form()],
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
    
    try:
        description_json = json.loads(description)
    except json.JSONDecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON for description")
    
    # Update only the modifiable fields
    announcement.first().title = title
    announcement.first().content = description_json
    announcement.first().url_name = new_url_name

    db.commit()
    db.refresh(announcement.first())
    return {"detail": "Announcement updated", "announcement": announcement.first()}

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


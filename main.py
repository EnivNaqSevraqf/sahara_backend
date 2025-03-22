from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, Query, Header, Body, File
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import ForeignKey, create_engine, Column, Integer, String, Enum, Table
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship, validates
from sqlalchemy.dialects.postgresql import JSONB, insert
from passlib.context import CryptContext
from datetime import datetime, timedelta
import jwt
import random
import string
from pydantic import BaseModel, EmailStr
from typing import List, Dict, Any
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
    gradeables = relationship("Gradeable", back_populates="creator")
    calendar_events = relationship("UserCalendarEvent", back_populates="creator")
    team_calendar_events = relationship("TeamCalendarEvent", back_populates="creator")

class Team(Base):
    __tablename__ = "teams"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    
    members = relationship("User", secondary="team_members", back_populates="teams")

class Form(Base):
    __tablename__ = "forms"
    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    description = Column(String, nullable=True)
    created_at = Column(String, default=datetime.now(timezone.utc).isoformat())

    target_type = Column(Enum(RoleType), nullable=False)  # Role or Team
    target_id = Column(Integer, nullable=False)  # Role ID or Team ID

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
    
    @validates("creator_id")
    def validate_creator(self, key, value):
        user = SessionLocal.query(User).filter_by(id=value).first()
        if user and user.role == RoleType.STUDENT:
            raise ValueError("Students cannot create announcements.")
        return value
    # content = Column(JSON)


class FormResponse(Base):
    __tablename__ = "form_responses"

    id = Column(Integer, primary_key=True)
    form_id = Column(Integer, ForeignKey("forms.id"), nullable=False)
    submitted_at = Column(String, default=datetime.now(timezone.utc).isoformat())
    response_data = Column(String, nullable=False)  # JSON or serialized response data

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
    if top_row:
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
    return "".join(random.choices(string.ascii_letters + string.digits, k=length))

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
def login(request: LoginRequest, db: Session = Depends(get_db)):
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

@app.post("/announcements/create") # TODO: Charan
def create_announcement():
    pass

@app.get("/announcements/") # TODO: Spandan
def get_announcements():
    pass

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
def get_people():
    pass


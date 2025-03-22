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

###
# Authentication
###

SECRET_KEY = secrets.token_hex(32)
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")





def resolve_token(token: str = Header(None)):
    try:
        payload = jwt.decode(token, "secret", algorithms=["HS256"])
        return payload["sub"]
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def check_user_permitted(user_id: int, role: RoleType):
    user = SessionLocal.query(User).filter_by(id=user_id).first()
    if user.role != role:
        raise HTTPException(status_code=403, detail="User does not have permission to access this resource")




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


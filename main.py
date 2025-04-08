import json
# Explicitly import FastAPI's Form and rename it to avoid conflicts
from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, Query, Header, Body, File, Form as FastAPIForm, WebSocket, WebSocketDisconnect, WebSocketException
from fastapi.responses import JSONResponse, Response, FileResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy import ForeignKey, create_engine, Column, Integer, String, Enum, Table, Text, DateTime, text, Float, Boolean, JSON
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
import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formatdate
from constants import DATABASE_URL
# Create uploads directory if it doesn't exist
os.makedirs("uploads", exist_ok=True)

# Import CSV processing functions from authentication/read_csv.py
sys.path.append(os.path.join(os.path.dirname(__file__), 'authentication'))
from read_csv import extract_student_data_from_content, extract_ta_data_from_content, CSVFormatError


# Database setup - postgres
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
# Association table for Team-User many-to-many relationship
team_members = Table(
    "team_members", Base.metadata,
    Column("team_id", Integer, ForeignKey("teams.id"), primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id"), primary_key=True)
) 
# Define the invites association table
invites = Table(
    "invites", Base.metadata,
    Column("team_id", Integer, ForeignKey("teams.id"), primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id"), primary_key=True),
    Column("invited_at", String, default=datetime.now(timezone.utc).isoformat())
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
    file_url = Column(String, nullable=True)  # URL path to the reference file
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
            if user and user.role.role == RoleType.STUDENT:
                raise ValueError("Only professors or TAs can create submittables.")
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

class Assignable(Base):
    __tablename__ = "assignables"
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
    creator = relationship("User", back_populates="assignables")
    assignments = relationship("Assignment", back_populates="assignable")

    @validates("creator_id")
    def validate_creator(self, key, value):
        with SessionLocal() as db:
            user = db.query(User).filter_by(id=value).first()
            if user and user.role.role == RoleType.STUDENT:
                raise ValueError("Only professors or TAs can create assignables.")
        return value

class Assignment(Base):
    __tablename__ = "assignments"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    submitted_on = Column(String, default=datetime.now(timezone.utc).isoformat())
    file_url = Column(String, nullable=False)  # URL path to the reference file
    original_filename = Column(String, nullable=False)
    assignable_id = Column(Integer, ForeignKey("assignables.id"), nullable=False)
    score = Column(Integer, nullable=True)  # Score received for this submission

    user = relationship("User", back_populates="assignments")
    assignable = relationship("Assignable", back_populates="assignments")

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    email = Column(String, nullable=False, unique=True)
    username = Column(String, nullable=False, unique=True)
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=False)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=True)
    hashed_password = Column(String, nullable=False)

    role = relationship("Role", back_populates="users")
    teams = relationship("Team", secondary="team_members", back_populates="members")
    responses = relationship("FormResponse", back_populates="user", lazy="joined")
    gradeables = relationship("Gradeable", back_populates="creator", lazy="joined")
    calendar_events = relationship("UserCalendarEvent", back_populates="creator", lazy="joined")
    team_calendar_events = relationship("TeamCalendarEvent", back_populates="creator", lazy="joined")
    skills = relationship("Skill", secondary=user_skills, back_populates="users")
    gradeable_scores = relationship("GradeableScores", back_populates="user", lazy="joined")
    submittables = relationship("Submittable", back_populates="creator", lazy="joined")
    assignables = relationship("Assignable", back_populates="creator", lazy="joined")
    assignments = relationship("Assignment", back_populates="user", lazy="joined")
    messages = relationship("Message", back_populates="sender", lazy="joined")
    feedback_submissions = relationship("FeedbackSubmission", foreign_keys="FeedbackSubmission.submitter_id", back_populates="submitter", lazy="joined")
    feedback_details = relationship("FeedbackDetail", foreign_keys="FeedbackDetail.member_id", back_populates="member", lazy="joined")
    invites = relationship("Team", secondary="invites", back_populates="invites")
    user_calendar_events = relationship("NewUserCalendarEvent", back_populates="user", lazy="joined")
    
    # @validates('skills')
    # def validate_skills(self, key, skill):
    #     with SessionLocal() as db:
    #         role = db.query(Role).filter_by(id=self.role_id).first()
    #         if role and role.role != RoleType.TA:
    #             raise ValueError("Only TAs can have skills.")
    #     return skill

class Team(Base):
    __tablename__ = "teams"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    
    members = relationship("User", secondary=team_members, back_populates="teams")
    skills = relationship("Skill", secondary=team_skills, back_populates="teams")
    submissions = relationship("Submission", back_populates="team") 
    # 
    feedback_submissions = relationship("FeedbackSubmission", back_populates="team")
    invites = relationship("User", secondary=invites, back_populates="invites")
    team_calendar_events = relationship("NewTeamCalendarEvent", back_populates="team", lazy="joined")

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

# team_members = Table(
#     "team_members", Base.metadata,
#     Column("team_id", Integer, ForeignKey("teams.id"), primary_key=True),
#     Column("user_id", Integer, ForeignKey("users.id"), primary_key=True)
# )
# invites = Table(
#     "invites", Base.metadata,
#     Column("team_id", Integer, ForeignKey("teams.id"), primary_key=True),
#     Column("user_id", Integer, ForeignKey("users.id"), primary_key=True),
#     Column("invited_at", String, default=datetime.now(timezone.utc).isoformat())
# )

class Announcement(Base):
    __tablename__ = "announcements"
    id = Column(Integer, primary_key=True)
    creator_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(String, default=lambda: datetime.now(timezone.utc).isoformat())
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
    events = Column(JSON, nullable=False)
    description = Column(String, nullable=False)
    start_time = Column(String, nullable=False)
    end_time = Column(String, nullable=False)
    created_at = Column(String, default=datetime.now(timezone.utc).isoformat())

class UserCalendarEvent(Base):
    __tablename__ = "user_calendar_events"
    id = Column(Integer, primary_key=True)
    events = Column(JSON, nullable=False)
    description = Column(String, nullable=False)
    start_time = Column(String, nullable=False)
    end_time = Column(String, nullable=False)
    creator_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
    created_at = Column(String, default=datetime.now(timezone.utc).isoformat())

    creator = relationship("User", back_populates="calendar_events", lazy="joined")

    @validates("creator_id")
    def validate_creator(self, key, value):
        with SessionLocal() as session:
            user = session.query(User).filter_by(id=value).first()
            if user and user.role.role == RoleType.STUDENT:
                raise ValueError("Students cannot create calendar events.")
        return value

class TeamCalendarEvent(Base):
    __tablename__ = "team_calendar_events"
    id = Column(Integer, primary_key=True)
    events = Column(JSON, nullable=False)
    description = Column(String, nullable=False)
    start_time = Column(String, nullable=False)
    end_time = Column(String, nullable=False)
    creator_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(String, default=datetime.now(timezone.utc).isoformat())

    creator = relationship("User", back_populates="team_calendar_events", lazy="joined")

    @validates("creator_id")
    def validate_creator(self, key, value):
        with SessionLocal() as session:
            user = session.query(User).filter_by(id=value).first()
            if user and user.role.role == RoleType.STUDENT:
                raise ValueError("Students cannot create calendar events.")
        return value
    
class Team_TA(Base):
    __tablename__ = "team_tas"
    id = Column(Integer, primary_key=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    ta_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    team = relationship("Team", backref="team_tas")
    ta = relationship("User", backref="ta_teams")

# class TeamInvites(Base):
#     __tablename__ = "team_invites"
#     id = Column(Integer, primary_key=True)
#     team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
#     user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
#     invited_at = Column(String, default=datetime.now(timezone.utc).isoformat())

#     user = relationship("User", backref="invites")
#     team = relationship("Team", backref="invitations")



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



class TeamSkill(Base):
    __tablename__ = "team_skills"

class UserSkill(Base):
    __tablename__ = "user_skills"
    
# class TeamCalendarEvent(Base):
#     __tablename__ = "team_calendar_events"
#     id = Column(Integer, primary_key=True)
#     events = Column(JSON, nullable=False)
#     description = Column(String, nullable=False)
#     start_time = Column(String, nullable=False)
#     end_time = Column(String, nullable=False)
#     creator_id = Column(Integer, ForeignKey("users.id"), nullable=False)
#     created_at = Column(String, default=datetime.now(timezone.utc).isoformat())

#     creator = relationship("User", back_populates="team_calendar_events", lazy="joined")

#     @validates("creator_id")
#     def validate_creator(self, key, value):
#         with SessionLocal() as session:
#             user = session.query(User).filter_by(id=value).first()
#             if user and user.role.role == RoleType.STUDENT:
#                 raise ValueError("Students cannot create calendar events.")
#         return value

class NewTeamCalendarEvent(Base):
    __tablename__ = "team_calendar"
    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    subtitle = Column(String, nullable=True)
    start = Column(String, nullable=False)
    end = Column(String, nullable=False)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)

    team = relationship("Team", back_populates="team_calendar_events", lazy="joined")
# class UserCalendarEvent(Base):
#     __tablename__ = "user_calendar_events"
#     id = Column(Integer, primary_key=True)
#     events = Column(JSON, nullable=False)
#     description = Column(String, nullable=False)
#     start_time = Column(String, nullable=False)
#     end_time = Column(String, nullable=False)
#     creator_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
#     created_at = Column(String, default=datetime.now(timezone.utc).isoformat())

#     creator = relationship("User", back_populates="calendar_events", lazy="joined")

#     @validates("creator_id")
#     def validate_creator(self, key, value):
#         with SessionLocal() as session:
#             user = session.query(User).filter_by(id=value).first()
#             if user and user.role.role == RoleType.STUDENT:
#                 raise ValueError("Students cannot create calendar events.")
#         return value

class NewUserCalendarEvent(Base):
    __tablename__ = "user_calendar"
    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    subtitle = Column(String, nullable=True)
    start = Column(String, nullable=False)
    end = Column(String, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    user = relationship("User", back_populates="user_calendar_events", lazy="joined")

    # @validates("user_id")
    # def validate_user(self, key, value):
    #     with SessionLocal() as session:
    #         user = session.query(User).filter_by(id=value).first()
    #         if user and user.role.role != RoleType.STUDENT:
    #             raise ValueError("Only students can create personal calendar events.")
    #     return value
# class GlobalCalendarEvent(Base):
#     __tablename__ = "global_calendar_events"
#     id = Column(Integer, primary_key=True)
#     events = Column(JSON, nullable=False)
#     description = Column(String, nullable=False)
#     start_time = Column(String, nullable=False)
#     end_time = Column(String, nullable=False)
#     created_at = Column(String, default=datetime.now(timezone.utc).isoformat())

class NewGlobalCalendarEvent(Base):
    __tablename__ = "global_calendar"
    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    subtitle = Column(String, nullable=True)
    start = Column(String, nullable=False)
    end = Column(String, nullable=False)
# Add these Pydantic models for request validation
class FeedbackDetailRequest(BaseModel):
    member_id: int
    contribution: float
    remarks: str

class FeedbackSubmissionRequest(BaseModel):
    team_id: int
    details: List[FeedbackDetailRequest]


# Define OTP database table
class UserOTP(Base):
    __tablename__ = "user_otps"
    
    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    hashed_otp = Column(String, nullable=False)
    expires_at = Column(String, nullable=False)  # ISO 8601 format
    
    # Relationship with User
    user = relationship("User", backref="otp_record")

# Course Config Table
class CourseConfig(Base):
    __tablename__ = "course_config"
    id = Column(Integer, primary_key=True)
    team_phase_enabled = Column(Boolean, default=True, nullable=False)
    discussions_enabled = Column(Boolean, default=True, nullable=False)
    feedback_enabled = Column(Boolean, default=True, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc))
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Relationship with the user who last updated the config
    updated_by_user = relationship("User", foreign_keys=[updated_by])

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

def reset_sequence(table_name: str, db: Session):
    """Reset the ID sequence for a table to start from MAX(id) + 1"""
    try:
        # First check if the table exists and has an id column
        check_id_query = text(f"""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = '{table_name}' AND column_name = 'id'
            );
        """)
        has_id = db.execute(check_id_query).scalar()
        
        if not has_id:
            print(f"  - Skipping {table_name} - no 'id' column found")
            return
            
        # Check if sequence exists for this table
        sequence_query = text(f"""
            SELECT pg_get_serial_sequence('{table_name}', 'id') AS seq_name;
        """)
        sequence_name = db.execute(sequence_query).scalar()
        
        if not sequence_name:
            print(f"  - Skipping {table_name} - no sequence found")
            return
            
        # Reset the sequence
        reset_query = text(f"""
            SELECT setval('{sequence_name}', 
                        (SELECT COALESCE(MAX(id), 0) + 1 FROM {table_name}), 
                        false);
        """)
        db.execute(reset_query)
        db.commit()
        print(f"  ✓ Reset sequence for {table_name}")
    except Exception as e:
        db.rollback()
        print(f"  ✗ Error resetting sequence for {table_name}: {str(e)}")

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

# Add this Pydantic model for the team name update request
class TeamNameUpdateRequest(BaseModel):
    name: str
    
    @validator('name')
    def validate_name(cls, v):
        if not v or len(v.strip()) < 3:
            raise ValueError("Team name must be at least 3 characters long")
        if len(v.strip()) > 100:
            raise ValueError("Team name cannot exceed 100 characters")
        return v.strip()
class CalendarEvent(BaseModel):
    start: str
    end: str
    title: str
    subtitle: str
    type: str
    # color: str = None
    # allDay: bool = False

class CalendarUpdateModel(BaseModel):
    events: List[CalendarEvent]
    # token: str = Header(None)
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

# Reset sequences for all tables
print("Resetting sequences...")
with engine.connect() as connection:
    # Get all table names from SQLAlchemy metadata
    table_names = Base.metadata.tables.keys()
    
    # Process each table in a separate transaction
    for table_name in table_names:
        # Create a new session for each table to isolate transactions
        with SessionLocal() as db:
            reset_sequence(table_name, db)
            
print("Sequences reset!")

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

# Create default professor (Indranil Saha)
def create_default_prof():
    with SessionLocal() as db:
        prof_role = db.query(Role).filter(Role.role == RoleType.PROF).first()
        if not prof_role:
            return  # Can't create user without role
        
        # Check if the professor already exists
        existing_prof = db.query(User).filter(User.email == "isaha@iitk.ac.in").first()
        if not existing_prof:
            # Create username from email
            username = "isaha"
            
            # Create the professor
            new_prof = User(
                name="Indranil Saha",
                email="isaha@iitk.ac.in",
                username=username,
                hashed_password=pwd_context.hash("password123"),  # Set a default password
                role_id=prof_role.id
            )
            db.add(new_prof)
            db.commit()

# Create default skills
def create_default_skills():
    with SessionLocal() as db:
        # Define the default skills with their properties
        default_skills = [
            {"name": "Java", "bgColor": "#f89820", "color": "#ffffff", "icon": "code"},
            {"name": "MongoDB", "bgColor": "#4DB33D", "color": "#ffffff", "icon": "database"},
            {"name": "Node.js", "bgColor": "#339933", "color": "#ffffff", "icon": "nodejs"},
            {"name": "Python", "bgColor": "#3776AB", "color": "#ffffff", "icon": "python"},
            {"name": "React", "bgColor": "#61DAFB", "color": "#000000", "icon": "react"},
            {"name": "Spring Boot", "bgColor": "#6DB33F", "color": "#ffffff", "icon": "spring"},
        ]
        
        # Check and create each skill if it doesn't exist
        for skill_data in default_skills:
            existing_skill = db.query(Skill).filter(Skill.name == skill_data["name"]).first()
            if not existing_skill:
                new_skill = Skill(
                    name=skill_data["name"],
                    bgColor=skill_data["bgColor"],
                    color=skill_data["color"],
                    icon=skill_data["icon"]
                )
                db.add(new_skill)
        
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
create_default_prof()  # Create Indranil Saha
create_default_skills()  

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
        reset_sequence("users", db)
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
    """Upload TAs from a CSV file with Name and Email columns"""
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
        
        # Print the first few lines for debugging
        print(f"CSV Content (first 100 chars): {content_str[:100]}")
        
        # Parse the CSV directly to get TAs
        reader = csv.DictReader(content_str.splitlines())
        required_headers = ['Name', 'Email']
        
        # Validate headers
        headers = reader.fieldnames
        print(f"CSV Headers: {headers}")
        
        if not headers:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Empty CSV file or invalid format"
            )
        
        for header in required_headers:
            if header not in headers:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, 
                    detail=f"CSV format error: Missing header: {header}"
                )
        
        tas = []
        for row in reader:
            if row.get('Name') and row.get('Email'):
                tas.append({
                    'Name': row['Name'],
                    'Email': row['Email']
                })
        
        print(f"Parsed {len(tas)} TAs from CSV")
        
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
                # Extract username from email
                username = ta['Email'].split('@')[0]
                print(f"Processing TA: {ta['Name']}, username: {username}")
                
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
                
                # Add to database
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
                db.rollback()  # Rollback on error
                print(f"Error processing TA {ta['Name']}: {str(e)}")
                errors.append(f"Error processing TA {ta['Name']}: {str(e)}")
        
        return {
            "message": f"Processed {len(created_tas)} TAs",
            "created_tas": created_tas,
            "errors": errors
        }
    
    except HTTPException as he:
        print(f"HTTP Exception: {he.detail}")
        raise he
    except Exception as e:
        import traceback
        print(f"Error in upload_tas: {str(e)}")
        print(traceback.format_exc())
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
    creator_name: Optional[str] = None

    class Config:
        orm_mode = True

@app.post('/announcements', status_code=status.HTTP_201_CREATED)
async def create(
    title: str = FastAPIForm(...),
    description: str = FastAPIForm(...),
    file: UploadFile = File(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        # Check if user is professor
        if current_user["role"].value != "prof":
            raise HTTPException(
                status_code=403,
                detail="Only professors can create announcements"
            )
            
        user = current_user["user"]
        # Create announcement
        announcement = Announcement(
            title=title,
            content=description,
            creator_id=user.id
        )

        #print("Here")

        # Handle file upload if provided
        if file:
            # Validate file size (50MB limit)
            if file.size > 50 * 1024 * 1024:
                raise HTTPException(
                    status_code=400,
                    detail="File size must be less than 50MB"
                )

            # Validate file type
            allowed_types = ['application/pdf', 'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'image/jpeg', 'image/png']
            if file.content_type not in allowed_types:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid file type. Please upload a PDF, Word document, or image (JPEG/PNG)"
                )

            # Generate unique filename
            file_extension = os.path.splitext(file.filename)[1]
            unique_filename = f"{uuid.uuid4()}{file_extension}"
            
            # Save file
            file_path = os.path.join("uploads", unique_filename)
            with open(file_path, "wb") as buffer:
                content = await file.read()
                buffer.write(content)
            
            announcement.url_name = unique_filename

        db.add(announcement)
        db.commit()
        db.refresh(announcement)


        return announcement
    except HTTPException as e:
        raise e
    except Exception as e:
        db.rollback()
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
    try:
        announcements = db.query(Announcement).order_by(Announcement.created_at.desc()).all()
        # Instead of returning creator id return creator name
        for announcement in announcements:
            creator = db.query(User).filter(User.id == announcement.creator_id).first()
            announcement.creator_name = creator.name if creator else f"User {announcement.creator_id}"
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

# @app.delete('/announcements/{id}', status_code=status.HTTP_204_NO_CONTENT)
# def destroy(id: int, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
#     try:
#         # Check if user is admin
#         if current_user["role"] not in [RoleType.PROF]:
#             raise HTTPException(
#                 status_code=403,
#                 detail="Only professors and teaching assistants can delete announcements"
#             )

#         announcement = db.query(Announcement).filter(Announcement.id == id).first()
#         if not announcement:
#             raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f'Announcement with id: {id} not found')
        
#         # Delete the associated file if it exists
#         if announcement.url_name:
#             file_path = os.path.join("uploads", announcement.url_name)
#             if os.path.exists(file_path):
#                 try:
#                     os.remove(file_path)
#                 except OSError:
#                     pass  # Ignore file deletion errors during cleanup
#             raise HTTPException(status_code=500, detail="Failed to delete announcement file")
        
#         # Delete the announcement from database
#         db.delete(announcement)
#         db.commit()
        
#         return {'message': 'Announcement deleted successfully'}
#     except Exception as e:
#         db.rollback()
#         raise HTTPException(status_code=500, detail=f"Error deleting announcement: {str(e)}")

@app.delete('/announcements/{id}', status_code=status.HTTP_204_NO_CONTENT)
def destroy(
    id: int, 
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
       
        if current_user["role"].value != "prof":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only professors can delete announcements")
        print("Here")
        announcement = db.query(Announcement).filter(Announcement.id == id).first()
        if not announcement:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f'Announcement with id: {id} not found')
        
        # Delete the associated file if it exists
        if announcement.url_name:
            file_path = os.path.join("uploads", announcement.url_name)
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except OSError:
                    pass  # Ignore file deletion errors during cleanup
        
        # Delete the announcement from database
        db.delete(announcement)
        db.commit()
        
        return {'message': 'Announcement deleted successfully'}
    except HTTPException as e:
        db.rollback()
        raise e
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
    # Get all teams and TAs
    teams = db.query(Team).all()
    tas = db.query(User).filter(User.role_id == 3).all()
    
    if not tas:
        raise HTTPException(status_code=400, detail="No TAs available")
    
    # Calculate maximum teams per TA
    max_teams_per_ta = (len(teams) * n) // len(tas)
    if (len(teams)*n)>len(tas)*max_teams_per_ta:
        max_teams_per_ta = 1 + max_teams_per_ta
    if max_teams_per_ta == 0:
        max_teams_per_ta = 1
    
    # Dictionary to track number of teams assigned to each TA
    ta_assignments = {ta.id: 0 for ta in tas}
    allocations = []
    all_matches = []

    # Calculate skill matches for all team-TA pairs
    for team in teams:
        # Get team's required skills
        team_skills = set([skill[0] for skill in db.query(TeamSkill.skill_id)
            .filter(TeamSkill.team_id == team.id).all()])
        
        for ta in tas:
            # Get TA's skills
            ta_skills = set([skill[0] for skill in db.query(UserSkill.skill_id)
                .filter(UserSkill.user_id == ta.id).all()])
            
            # Calculate skill match score
            match_score = len(team_skills.intersection(ta_skills))
            
            if match_score > 0:  # Only consider pairs with at least one skill match
                all_matches.append({
                    "team_id": team.id,
                    "ta_id": ta.id,
                    "match_score": match_score
                })

    # Sort matches by match score in descending order
    all_matches.sort(key=lambda x: x["match_score"], reverse=True)

    # Create initial allocations based on best matches
    team_allocations = {team.id: [] for team in teams}

    # First pass: Assign TAs based on best skill matches
    for match in all_matches:
        team_id = match["team_id"]
        ta_id = match["ta_id"]

        # Check if team needs more TAs and TA hasn't reached their limit
        if (len(team_allocations[team_id]) < n and 
            ta_assignments[ta_id] < max_teams_per_ta):
            team_allocations[team_id].append(ta_id)
            ta_assignments[ta_id] += 1

    # Second pass: Fill remaining slots if needed
    for team_id, assigned_tas in team_allocations.items():
        while len(assigned_tas) < n:
            # Find TA with fewest assignments who isn't already assigned to this team
            available_ta = min(
                (ta_id for ta_id in ta_assignments if ta_id not in assigned_tas),
                key=lambda x: ta_assignments[x],
                default=None
            )
            
            if available_ta and ta_assignments[available_ta] < max_teams_per_ta:
                assigned_tas.append(available_ta)
                ta_assignments[available_ta] += 1
            else:
                break  # No more available TAs

    # Format the allocations
    for team_id, assigned_tas in team_allocations.items():
        allocations.append({
            "team_id": team_id,
            "assigned_ta_ids": assigned_tas
        })

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
        # Get all teams with their skills and TAs
        teams = db.query(Team).all()
        results = []
        
        for team in teams:
            # Get team skills
            skills = db.query(Skill).join(team_skills).filter(team_skills.c.team_id == team.id).all()
            
            # Get assigned TAs
            tas = (
                db.query(User)
                .join(Team_TA, User.id == Team_TA.ta_id)
                .filter(Team_TA.team_id == team.id)
                .all()
            )
            
            results.append({
                "team_id": team.id,
                "team_name": team.name,
                "skills": [
                    {
                        "id": skill.id,
                        "name": skill.name,
                        "bgColor": skill.bgColor,
                        "color": skill.color,
                        "icon": skill.icon
                    }
                    for skill in skills
                ],
                "tas": [
                    {
                        "id": ta.id,
                        "name": ta.name
                    }
                    for ta in tas
                ]
            })
        
        return {"teams": results}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Calendar
    # token: str = Header(None)

# @app.post("/calendar/update")
# def update_calendar(
#     calendar_update_model: CalendarUpdateModel,
#     db: Session = Depends(get_db),
#     # user_id: int = Depends(resolve_token)
# ):
#     # user = db.query(User).filter_by(id=user_id).first()
#     print(calendar_update_model.events)
#     global_events = calendar_update_model.events
#     # global_events, personal_events, team_events = split_events(calendar_update_model.events)
#     print(global_events)
#     overwrite_global_events(global_events, db)
#     return {"message": "Calendar updated"}
#     # if user.role == RoleType.PROF:
#     #     overwrite_global_events(events, db)
#     # elif user.role == RoleType.STUDENT:
#     #     overwrite_personal_events(user, events, db)
#     # elif user.role == RoleType.TA:
#     #     overwrite_team_events(user, events, db)
#     # return {"message": "Calendar updated"}
#     # if the role is admin
#     # select all the global events

#     # overwrite_global_events



    
#     pass

@app.get("/calendar")
def get_calendar(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    # user_id: int = Depends(resolve_token)
):
    user = current_user["user"]
    role = current_user["role"]

    events = []
    # Get the global events
    global_events_db = db.query(NewGlobalCalendarEvent).all()
    global_events = []
    for event in global_events_db:
        global_events.append({
            "event_id": f"g{event.id}",
            "title": event.title,
            "subtitle": event.subtitle,
            "start": event.start,
            "end": event.end,
            "type": "global"
        })
        events += global_events
    
    user_events_db = db.query(NewUserCalendarEvent).filter_by(user_id=user.id).all()
    user_events = []
    for event in user_events_db:
        user_events.append({
            "event_id": f"p{event.id}",
            "title": event.title,
            "subtitle": event.subtitle,
            "start": event.start,
            "end": event.end,
            "type": "personal"
        })
        events += user_events
    if user.team_id:
        team_events_db = db.query(NewTeamCalendarEvent).filter_by(team_id=user.team_id).all()
        team_events = []
        for event in team_events_db:
            team_events.append({
                "event_id": f"t{event.id}",
                "title": event.title,
                "subtitle": event.subtitle,
                "start": event.start,
                "end": event.end,
                "type": "team"
            })
        events += team_events
    
    
    
    return JSONResponse(status_code=201, content=events)
    # return {"message": "Calendar retrieved", "events": global_events}

@app.post("/calendar/create")
def create_calendar(
    calendar_event: CalendarEvent,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    # user_id: int = Depends(resolve_token)
):
    
    user = current_user["user"]
    role = current_user["role"]

    if calendar_event.type == "global":
        # Check if the user is professor
        if role != RoleType.PROF:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to create global events")
        # Create the global event
        new_event = NewGlobalCalendarEvent(
            title=calendar_event.title,
            subtitle=calendar_event.subtitle,
            start=calendar_event.start,
            end=calendar_event.end
        )

        db.add(new_event)
        db.commit()
        db.refresh(new_event)

        event_json = {
            "event_id": f"g{new_event.id}",
            "title": new_event.title,
            "subtitle": new_event.subtitle,
            "start": new_event.start,
            "end": new_event.end,
            "type": "global"
        }

        return JSONResponse(status_code=201, content={"message": "Global event created", "event": event_json})
    if calendar_event.type == "personal":
        new_personal_event = NewUserCalendarEvent(
            title=calendar_event.title,
            subtitle=calendar_event.subtitle,
            start=calendar_event.start,
            end=calendar_event.end,
            user_id=user.id
        )
        db.add(new_personal_event)
        db.commit()
        db.refresh(new_personal_event)

        event_json = {
            "event_id": f"p{new_personal_event.id}",
            "title": new_personal_event.title,
            "subtitle": new_personal_event.subtitle,
            "start": new_personal_event.start,
            "end": new_personal_event.end,
            "type": "personal"
        }

        return JSONResponse(status_code=201, content={"message": "Personal event created", "event": event_json})
    if calendar_event.type == "team":
        # Check if the user is in a team
        if not user.team_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to create team events")
        # Create the team event
        new_team_event = NewTeamCalendarEvent(
            title=calendar_event.title,
            subtitle=calendar_event.subtitle,
            start=calendar_event.start,
            end=calendar_event.end,
            team_id=user.team_id
        )
        db.add(new_team_event)
        db.commit()
        db.refresh(new_team_event)

        event_json = {
            "event_id": f"t{new_team_event.id}",
            "title": new_team_event.title,
            "subtitle": new_team_event.subtitle,
            "start": new_team_event.start,
            "end": new_team_event.end,
            "type": "team"
        }

        return JSONResponse(status_code=201, content={"message": "Team event created", "event": event_json})

        # Check if the user is a student or TA
        # if role not in [RoleType.STUDENT, RoleType.TA]:
            # raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to create personal events")
        # Create the personal event
        # new_event = NewGlobalCalendarEvent(
        #     title=calendar_event.title,
        #     subtitle=calendar_event.subtitle,
        #     start=calendar_event.start,
        #     end=calendar_event.end
        # )

        # db.add(new_event)
        # db.commit()
        # db.refresh(new_event)

        # return JSONResponse(status_code=201, content={"message": "Personal event created", "event": new_event})

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
@app.delete("/calendar/delete/{event_id}")
def delete_calendar_event(
    event_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    # user_id: int = Depends(resolve_token)
):
    user = current_user["user"]
    role = current_user["role"]
    if event_id[0] == "g":
        # Check if the user is professor
        if role != RoleType.PROF:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete global events")
        event_id = int(event_id[1:])
        # Check if the event exists
        event = db.query(NewGlobalCalendarEvent).filter_by(id=event_id).first()
        if not event:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
        
        # Delete the event
        db.delete(event)
        db.commit()
        return JSONResponse(status_code=200, content={"message": "Event deleted"})
    elif event_id[0] == "p":
        # Check if event exists
        event_id = int(event_id[1:])
        event = db.query(NewUserCalendarEvent).filter_by(id=event_id).first()
        if not event:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
        # Check if the user is the creator of the event
        if event.user_id != user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete this event")
        
        # Delete the event
        db.delete(event)
        db.commit()
        return JSONResponse(status_code=200, content={"message": "Event deleted"})

    elif event_id[0] == "t":
        event_id = int(event_id[1:])
        # Check if the user is in a team
        if not user.team_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete team events")
        # Check if event exists
        event = db.query(NewTeamCalendarEvent).filter_by(id=event_id).first()
        if not event:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
        
        # Check if the user is the creator of the event
        if event.team_id != user.team_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete this event")




        event = db.query(NewTeamCalendarEvent).filter_by(id=event_id).first()
        if not event:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
        

        db.delete(event)
        db.commit()
        return JSONResponse(status_code=200, content={"message": "Event deleted"})
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid event ID")

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
async def api_create_form(form_data: FormCreateRequest, db: Session = Depends(get_db)):
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


@app.get("/teams")
async def get_student_team(
    current_user: dict[User, str] = Depends(get_current_user),
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
        if user.teams:
            
            team = user.teams[0]  # Get the student's team
            # Get all team members including the current user
            team_members = [
                {
                    "id": member.id,
                    "name": member.name,
                    "email": member.email,
                    "is_current_user": member.id == user.id
                }
                for member in team.members
            ]

            skills = team.skills
            skill_data = []
            for skill in skills:
                skill_data.append({
                    "id": skill.id,
                    "name": skill.name,
                    "bgColor": skill.bgColor,
                    "color": skill.color,
                    "icon": skill.icon
                })
            all_skills = db.query(Skill).all()
            all_skills_data = []
            for skill in all_skills:
                all_skills_data.append({
                    "id": skill.id,
                    "name": skill.name,
                    "bgColor": skill.bgColor,
                    "color": skill.color,
                    "icon": skill.icon
                })
            return {
                "has_team": True,
                "team_id": team.id,
                "team_name": team.name,
                "members": team_members,
                "skills": skill_data,
                "all_skills":  all_skills
            }
        else:
            invites = user.invites
            # invites = db.query(TeamInvites).filter(TeamInvites.user_id == user.id).all()
            invite_data = []
            for team in invites:
                data = {}
                data["team_id"] = team.id
                data["team_name"] = team.name
                data["team_members"] = [member.name for member in team.members]
                invite_data.append(data)

            return {
                "has_team": False,
                "invites": invite_data
            }

    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@app.put("/teams/skills")
def update_team_skills(
    skills: List[int],
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Update team skills
    """
    try:
    # if 1:
        user = current_user["user"]
        if current_user["role"] != RoleType.STUDENT:
            raise HTTPException(status_code=403, detail="Only students can access this endpoint")
        
        if not user.teams:
            raise HTTPException(status_code=404, detail="User has no team assigned")
        team = user.teams[0]  # Get the student's team
        if not team:
            raise HTTPException(status_code=404, detail="Team not found")
        
        # Clear existing skills and assign new ones
        team.skills = []
        for skill_id in skills:
            skill = db.query(Skill).filter(Skill.id == skill_id).first()
            if skill:
                team.skills.append(skill)
        db.commit()
        
        return JSONResponse(status_code=200, content={"message": "Team skills updated successfully"})
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

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

@app.put("/teams/name")
async def update_team_name(
    request: TeamNameUpdateRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Extract user and role
    user = current_user["user"]
    role = current_user["role"]
    
    # Verify that the user is a student
    if role != RoleType.STUDENT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only students can update team names"
        )
    
    # Get the user's team
    teams = user.teams
    if not teams:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="You are not a member of any team"
        )
    
    # Update the team name
    team = teams[0]  # Assuming a student is only in one team
    team.name = request.name
    
    try:
        db.commit()
        return {
            "message": "Team name updated successfully",
            "team_id": team.id,
            "team_name": team.name
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update team name: {str(e)}"
        )

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
        unadded_users = []
        for row_num, row in enumerate(csv_reader, start=2):
            try:
                # # Extract and validate username
                # username = row['username'].strip()
                # Extract and validate roll no
                RollNo = row['RollNo'].strip()
                if not RollNo:
                    continue
                
                # Extract and validate score
                try:
                    score = int(row['score'])
                    if score < 0 or score > max_points:
                        raise ValueError(f"Score must be between 0 and {max_points}")
                except ValueError:
                    # TODO add the code for skipped these users
                    continue
                    raise ValueError(f"Invalid score format in row {row_num}")
                
                # Get user ID from roll number
                user = db.query(User).filter(User.id == RollNo).first()
            
                if not user:
                    unadded_users.append(user)
                    continue
                print("Added user id:", user.id)
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
            "gradeable_id": submission.gradeable_id,
            "user_id": submission.user_id, 
            "name": submission.user.name,
            #"submitted_at": submission.submitted_at,
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
    team = user.teams[0] if user.teams else None
    if not user or not team:
        raise HTTPException(status_code=400, detail="User must be part of a team to submit")

    # Check if team already has a submission
    existing_submission = db.query(Submission).filter(
        Submission.team_id == team.id,
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
        team_id=team.id,
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
        if role == RoleType.PROF or role == RoleType.TA:
            # Professors can download any submission
            pass
        elif role == RoleType.STUDENT:
            # Students can only download their team's submission
            team = user.teams[0] if user.teams else None
            if not team.id or team.id != submission.team_id:
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
        team = user.teams[0] if user.teams else None
        if team is None:
            return {
                "team_id": None,
                "upcoming": [],
                "open": [],
                "closed": []
            }
        team_submissions = {}
        if team.id:
            submissions = db.query(Submission).filter(Submission.team_id == team.id).all()
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
                    "id": 1,  # Using a placeholder ID for now
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
            "team_id": team.id,
            "upcoming": upcoming,
            "open": open_submittables,
            "closed": closed
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching submittables: {str(e)}")

@app.get("/submittables/all")
async def get_all_submittables(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get all submittables categorized by status for professors or TAs"""
    try:
        # Check if the user is a professor or TA
        if current_user["role"] not in [RoleType.PROF, RoleType.TA]:
            raise HTTPException(
                status_code=403,
                detail="Only professors or TAs can access this endpoint"
            )

        # Fetch all submittables
        submittables = db.query(Submittable).all()

        # Categorize submittables
        now = datetime.now(timezone.utc)
        upcoming = []
        open_submittables = []
        closed = []

        for submittable in submittables:
            opens_at = datetime.fromisoformat(submittable.opens_at) if submittable.opens_at else None
            deadline = datetime.fromisoformat(submittable.deadline)

            formatted_submittable = {
                "id": submittable.id,
                "title": submittable.title,
                "description": submittable.description,
                "opens_at": submittable.opens_at,
                "deadline": submittable.deadline,
                "max_score": submittable.max_score,
                "created_at": submittable.created_at,
                "reference_files": [{
                    "file_url": submittable.file_url,
                    "original_filename": submittable.original_filename
                }] if submittable.file_url else []
            }

            if opens_at and now < opens_at:
                upcoming.append(formatted_submittable)
            elif now > deadline:
                closed.append(formatted_submittable)
            else:
                open_submittables.append(formatted_submittable)

        # Return categorized submittables
        return {
            "upcoming": upcoming,
            "open": open_submittables,
            "closed": closed
        }
    except HTTPException as he:
        raise he
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
    #file: UploadFile = File(...),
    file: UploadFile = File(None),
    db: Session = Depends(get_db),
    token: str = Depends(prof_or_ta_required)
):
    """Create a new submittable with a reference file"""
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

        # Save the reference file
        file_path = None
        if file:
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
            max_score=max_score,  # Add max_score to submittable creation
            creator_id=user.id,
            file_url=file_path,  # URL path without leading slash
            original_filename=file.filename
        )
        
        db.add(new_submittable)
        db.commit()
        db.refresh(new_submittable)

        # Return JSON response with proper structure
        return JSONResponse(
            status_code=201,
            content={
                "message": "Submittable created successfully",
                "submittable": {
                    "id": new_submittable.id,
                    "title": new_submittable.title,
                    "opens_at": new_submittable.opens_at,
                    "deadline": new_submittable.deadline,
                    "description": new_submittable.description,
                    "max_score": new_submittable.max_score,  # Include max_score in response
                    "created_at": new_submittable.created_at,
                    "reference_files": [{
                        "original_filename": new_submittable.original_filename
                    }] if new_submittable.file_url else [],
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
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)  # Clean up file if validation fails
        raise he
    except Exception as e:
        db.rollback()
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)  # Clean up file if something went wrong
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
        if current_user["role"] == RoleType.STUDENT:
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
    token: str = Depends(prof_or_ta_required)
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
    opens_at: Optional[str] = FastAPIForm(None),
    file: Optional[UploadFile] = None,
    db: Session = Depends(get_db),
    token: str = Depends(prof_or_ta_required)
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
        team = user.teams[0] if user.teams else None
        if current_user["role"] == RoleType.STUDENT:
            # For students, check if they belong to the team that submitted
            if team.id != submission.team_id:
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
        # First check if feedback is enabled
        config = db.query(CourseConfig).first()
        if not config or not config.feedback_enabled:
            raise HTTPException(
                status_code=403,
                detail="Feedback is currently disabled. You cannot submit feedback at this time."
            )
            
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

# this is to grade a submission, done by profs
@app.put("/submissions/{submission_id}/grade")
async def grade_submission(
    submission_id: int,
    score: int = FastAPIForm(...),
    db: Session = Depends(get_db),
    token: str = Depends(prof_or_ta_required)
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

# this is to grade a submission, done by profs
@app.put("/submissions/{submission_id}/grade")
async def grade_submission(
    submission_id: int,
    score: int = FastAPIForm(...),
    db: Session = Depends(get_db),
    token: str = Depends(prof_or_ta_required)
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
    # First check if discussions are enabled
    config = db.query(CourseConfig).first()
    if not config or not config.discussions_enabled:
        raise HTTPException(
            status_code=403,
            detail="Discussions are currently disabled. You cannot access discussions at this time."
        )

    user = current_user_data["user"]
    if not user:
        raise HTTPException(status_code=404, detail=f"User not found: {user.name}")

    channels = []
    
    # Add global channel for all users
    global_channel = db.query(Channel).filter(Channel.type == 'global').first()
    if not global_channel:
        global_channel = Channel(
            name='Global Chat',
            type='global'
        )
        db.add(global_channel)
        db.commit()
        db.refresh(global_channel)
    
    channels.append(global_channel)

    # For professors: add only ta-team channels
    if user.role.role == RoleType.PROF:
        ta_team_channels = db.query(Channel).filter(Channel.type == 'ta-team').all()
        channels.extend(ta_team_channels)
    
    # For students: add their team channel and team-TA channel if they exist
    elif user.role.role == RoleType.STUDENT and user.teams:
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
    elif user.role.role == RoleType.TA:
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
        # Only students can access team channels
        return user.team_id == channel.team_id
        
    # For TA-team channels:
    if channel.type == 'ta-team':
        # Professors can access all TA-team channels
        if user.role.role == RoleType.PROF:
            return True
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
    # First check if discussions are enabled
    config = db.query(CourseConfig).first()
    if not config or not config.discussions_enabled:
        raise HTTPException(
            status_code=403,
            detail="Discussions are currently disabled. You cannot access discussions at this time."
        )

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
    # First check if discussions are enabled
    config = db.query(CourseConfig).first()
    if not config or not config.discussions_enabled:
        raise HTTPException(
            status_code=403,
            detail="Discussions are currently disabled. You cannot access discussions at this time."
        )

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
    # First check if discussions are enabled
    config = db.query(CourseConfig).first()
    if not config or not config.discussions_enabled:
        raise HTTPException(
            status_code=403,
            detail="Discussions are currently disabled. You cannot access discussions at this time."
        )

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
    # First check if discussions are enabled
    config = db.query(CourseConfig).first()
    if not config or not config.discussions_enabled:
        raise HTTPException(
            status_code=403,
            detail="Discussions are currently disabled. You cannot access discussions at this time."
        )

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

@app.post("/teams/upload-csv/")
async def upload_csv(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="Invalid file format. Please upload a CSV file.")
    try:
        contents = await file.read()
        text_contents = contents.decode('utf-8')
        df = pd.read_csv(StringIO(text_contents))
        
        # Validate required columns
        required_columns = ['RollNo', 'TeamID']
        for column in required_columns:
            if column not in df.columns:
                raise HTTPException(status_code=400, detail=f"Missing required column: {column}")
        
        # Group students by team ID
        team_to_users = {}
        for _, row in df.iterrows():
            roll_no = row['RollNo']
            team_id = row['TeamID']
            
            # Skip rows with empty team IDs
            if pd.isna(team_id) or pd.isna(roll_no):
                continue
            
            team_id = int(team_id)
            if team_id not in team_to_users:
                team_to_users[team_id] = []
            
            # Find the user with this roll number
            user = db.query(User).filter(User.id == roll_no).first()
            if not user:
                raise HTTPException(status_code=400, detail=f"User with Roll No {roll_no} not found")
            
            team_to_users[team_id].append(user)
        
        # Create or update teams
        created_teams = []
        updated_teams = []
        for team_id, users in team_to_users.items():
            print("Handling team id:", team_id)
            # Check if team already exists
            team = db.query(Team).filter(Team.id == team_id).first()
            
            if team:
                # Update existing team
                for user in users:
                    if user not in team.members:
                        team.members.append(user)
                        user.team_id = team.id
                updated_teams.append(team_id)
            else:
                # Create new team
                team = Team(id=team_id, name=f"Team {team_id}")
                db.add(team)
                db.flush()  # Get the ID without committing
                
                for user in users:
                    team.members.append(user)
                    user.team_id = team.id
                created_teams.append(team_id)
        
        db.commit()
        
        return {
            "message": "Teams created and updated successfully",
            "created_teams": created_teams,
            "updated_teams": updated_teams,
            "total_teams": len(team_to_users),
            "total_students_assigned": sum(len(users) for users in team_to_users.values())
        }
    except HTTPException as e:
        db.rollback()
        raise e
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error processing CSV: {str(e)}")

    
    # try:
    #     # Save the uploaded file to a temporary location
    #     temp_file_path = f"temp_{file.filename}"
    #     with open(temp_file_path, "wb") as temp_file:
    #         temp_file.write(file.file.read())

    #     # Read the CSV file using pandas
    #     df = pd.read_csv(temp_file_path)

    #     # Validate the CSV format
    #     required_columns = ['team_name', 'member1', 'member2', 'member3', 'member4', 'member5', 'member6', 'member7', 'member8', 'member9', 'member10']
    #     print(df.columns)
    #     for _column_name in required_columns:
    #         if _column_name not in df.columns:
    #             raise HTTPException(status_code=400, detail=f"Invalid CSV format. Missing column: {_column_name}")

    #     # Check if all members exist in the Users database and perform other checks
    #     team_names = set()
    #     members_set = list()
    #     for _, row in df.iterrows():
    #         team_name = row['team_name']
    #         members = []
    #         for i in range(1, 11):
    #             member = row[f'member{i}']
    #             if pd.notna(member) and member.strip():  # Add check for empty strings
    #                 members.append(member)

    #         if team_name in team_names:
    #             raise HTTPException(status_code=400, detail=f"Invalid file: Duplicate team name '{team_name}' found.")
            
    #         team_names.add(team_name)

    #         for member_name in members:
    #             user = db.query(User).filter_by(username=member_name).first()
    #             if not user:
    #                 raise HTTPException(status_code=400, detail=f"Invalid file: User '{member_name}' does not exist in the database.")
    #             if user.team_id:
    #                 raise HTTPException(status_code=400, detail=f"Invalid file: User '{member_name}' is already assigned to a team.")
    #             if member_name in members_set:
    #                 raise HTTPException(status_code=400, detail=f"Invalid file: User '{member_name}' is assigned to multiple teams.")
    #         members_set.append(members)

    #     team_names = list(team_names)
    #     print("Team names: ", team_names)
    #     print("Members set:", members_set)
        
    #     for i in range(len(team_names)):
    #         team_name = team_names[i]
    #         members = members_set[i]
    #         # print(members)
    #         # Create and save the team first
    #         team = Team(name=team_name)
    #         db.add(team)
    #         db.commit()  # Commit to get the team ID
    #         db.refresh(team)  # Make sure we have the latest data including the ID
            
    #         # Now add users to the team with the valid team ID
    #         for member in members:
    #             user = db.query(User).filter_by(username=member).first()
    #             print("Over here")
    #             if user:
    #                 team.members.append(user)
    #                 user.team_id = team.id  # Now team.id is valid
            
    #         db.commit()  # Commit changes for this team's users

    #     # Clean up the temporary file
    #     os.remove(temp_file_path)

    #     return {"detail": "File uploaded and data saved successfully!"}
    # except Exception as e:
    #     db.rollback()  # In case of error, rollback
    #     raise HTTPException(status_code=500, detail=str(e))
    


    # outdated code
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

class InviteUserModel(BaseModel):
    user_id: int

class TeamCreateModel(BaseModel):
    name: str

class JoinTeamModel(BaseModel):
    team_id: int

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
            # For security, we return a similar message but with a special status code
            # that the frontend can use to show a helpful message
            print(f"OTP request for non-existent email: {request.email}")
            return {
                "message": "If the email exists in our system, a verification code has been sent. Please check your spam folder if you don't see it in your inbox.",
                "status": "user_not_found"  # Changed this to be more semantic
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
        # First check if feedback is enabled
        config = db.query(CourseConfig).first()
        if not config or not config.feedback_enabled:
            raise HTTPException(
                status_code=403,
                detail="Feedback is currently disabled. You cannot submit feedback at this time."
            )

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

# assignables start here
# this is to submit file for an assignable, done by students
@app.post("/assignables/{assignable_id}/submit")
async def submit_file(
    assignable_id: int,
    file: UploadFile = File(...),  # Now accepts a single file
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Submit a file for an assignable.
    Only one assignment per submittable per user is allowed.
    """
    # Get the submittable
    assignable = db.query(Assignable).filter(Assignable.id == assignable_id).first()
    if not assignable:
        raise HTTPException(status_code=404, detail="Assignable not found")

    # Check if user already has a submission
    user = db.query(User).filter(User.id == current_user["user"].id).first()
    existing_assignment = db.query(Assignment).filter(
        Assignment.user_id == user.id,
        Assignment.assignable_id == assignable_id
    ).first()

    if existing_assignment:
        raise HTTPException(
            status_code=400, 
            detail="Your team has already submitted a file for this submittable. Please delete the existing submission first."
        )

    # Check if submission is allowed based on opens_at and deadline
    now = datetime.now(timezone.utc)
    opens_at = datetime.fromisoformat(assignable.opens_at) if assignable.opens_at else None
    deadline = datetime.fromisoformat(assignable.deadline)

    if opens_at and now < opens_at:
        raise HTTPException(status_code=400, detail="Submission period has not started yet")
    if now > deadline:
        raise HTTPException(status_code=400, detail="Submission deadline has passed")

    # Generate a unique filename
    file_extension = os.path.splitext(file.filename)[1]
    unique_filename = f"assignment_{uuid.uuid4()}{file_extension}"
    file_path = os.path.join("uploads", unique_filename)

    # Save the file
    try:
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")

    # Create submission record
    assignment = Assignment(
        user_id=user.id,
        file_url=file_path,
        original_filename=file.filename,
        assignable_id=assignable_id,
        score=None  # Initialize score as None since it hasn't been graded yet
    )

    try:
        db.add(assignment)
        db.commit()
        db.refresh(assignment)
        return {
            "message": "File submitted successfully",
            "assignment_id": assignment.id,
            "original_filename": assignment.original_filename,
            "max_score": assignable.max_score,  # Include max_score in response
            "score": assignment.score  # Include current score (will be None for new submissions)
        }
    except Exception as e:
        # If database operation fails, delete the uploaded file
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=500, detail=f"Failed to create assignment record: {str(e)}")
    
# this is to download the file for an assignment, done by profs and students
@app.get("/assignments/{assignment_id}/download")
async def download_assignment(
    assignment_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Download a submission file"""
    try:
        assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
        if not assignment:
            raise HTTPException(status_code=404, detail="Assignment not found")
        
        user = current_user["user"]
        role = current_user["role"]
        
        # Check permissions
        if role == RoleType.PROF or role == RoleType.TA:
            # Professors can download any submission
            pass
        elif role == RoleType.STUDENT:
            # Students can only download their submission
            if not user.id or user.id != assignment.user_id:
                raise HTTPException(status_code=403, detail="Not authorized to download this submission")
        else:
            raise HTTPException(status_code=403, detail="Not authorized to download submissions")
        
        # Get the file path
        local_path = assignment.file_url.lstrip('/')
        if not os.path.exists(local_path):
            raise HTTPException(status_code=404, detail="File not found")
        
        # Return the file directly
        return FileResponse(
            local_path,
            filename=assignment.original_filename,
            media_type="application/octet-stream"
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error downloading submission: {str(e)}")
    
# this is to get all submittables categorized by status, done by students and profs
@app.get("/assignables/")
async def get_assignables(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get all assignables categorized by status"""
    try:
        print("started fetching data")
        print(datetime.now(timezone.utc))
        # Get all submittables
        assignables = db.query(Assignable).all() 
        print(datetime.now(timezone.utc))
        assignables = db.query(Assignable).all() 
        print(datetime.now(timezone.utc))
        # Get user's team submissions
        user = current_user["user"]
        print(datetime.now(timezone.utc))
        user_assignments = {}
        print(datetime.now(timezone.utc))
        if user.id:
            assignments = db.query(Assignment).filter(Assignment.user_id == user.id).all()
            user_assignments = {s.assignable_id: s for s in assignments}
        print(datetime.now(timezone.utc))
        print("fetched data")
        # Helper function to format submittable
        def format_assignable(s):
            assignment = user_assignments.get(s.id)
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
                    "has_submitted": bool(assignment),
                    "submission_id": assignment.id if assignment else None,
                    "submitted_on": assignment.submitted_on if assignment else None,
                    "original_filename": assignment.original_filename if assignment else None,
                    "score": assignment.score if assignment else None  # Add score from submission
                }
            }

        # Categorize submittables
        now = datetime.now(timezone.utc)
        upcoming = []
        open_assignables = []
        closed = []

        for s in assignables:
            formatted = format_assignable(s)
            opens_at = datetime.fromisoformat(s.opens_at) if s.opens_at else None
            deadline = datetime.fromisoformat(s.deadline)

            if opens_at and now < opens_at:
                upcoming.append(formatted)
            elif now > deadline:
                closed.append(formatted)
            else:
                open_assignables.append(formatted)

        return {
            "upcoming": upcoming,
            "open": open_assignables,
            "closed": closed
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching assignables: {str(e)}")
    
# this is to download the reference file for an assignable, done by students and profs
@app.get("/assignables/{assignable_id}/reference-files/download")
async def download_reference_file(
    assignable_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Download a reference file for a submittable"""
    try:
        # Get the submittable
        assignable = db.query(Assignable).filter(Assignable.id == assignable_id).first()
        if not assignable:
            raise HTTPException(status_code=404, detail="Assignable not found")

        if not assignable.file_url:
            raise HTTPException(status_code=404, detail="No reference file found")

        # Check if file exists
        if not os.path.exists(assignable.file_url):
            raise HTTPException(status_code=404, detail="File not found on server")

        # Return the file
        return FileResponse(
            assignable.file_url,
            media_type='application/octet-stream',
            filename=assignable.original_filename
        )

    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error downloading file: {str(e)}")
    
# this is to create a new submittable, done by profs
@app.post("/assignables/create")
async def create_assignable(
    title: str = FastAPIForm(...),
    deadline: str = FastAPIForm(...),
    description: str = FastAPIForm(...),
    max_score: int = FastAPIForm(...),  # Add max_score parameter
    opens_at: Optional[str] = FastAPIForm(None),
    file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    token: str = Depends(prof_or_ta_required)
):
    """Create a new assignable with an optional reference file"""
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
        assignable = Assignable(
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
            assignable.file_url = file_path
            assignable.original_filename = file.filename

        # Add to database
        db.add(assignable)
        db.commit()
        db.refresh(assignable)

        # Return JSON response with proper structure
        return JSONResponse(
            status_code=201,
            content={
                "message": "Submittable created successfully",
                "submittable": {
                    "id": assignable.id,
                    "title": assignable.title,
                    "opens_at": assignable.opens_at,
                    "deadline": assignable.deadline,
                    "description": assignable.description,
                    "max_score": assignable.max_score,  # Include max_score in response
                    "created_at": assignable.created_at,
                    "reference_files": [{
                        "original_filename": assignable.original_filename
                    }] if assignable.file_url else [],
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
        raise HTTPException(status_code=500, detail=f"Error creating assignable: {str(e)}")

# this is to get details of a specific assignable, done by students and profs
@app.get("/assignables/{assignable_id}")
async def get_assignable(
    assignable_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get details of a specific assignanle"""
    try:
        assignable = db.query(Assignable).filter(Assignable.id == assignable_id).first()
        if not assignable:
            raise HTTPException(status_code=404, detail="Assignable not found")
        
        return JSONResponse(status_code=200, content={
            "id": assignable.id,
            "title": assignable.title,
            "opens_at": assignable.opens_at,
            "deadline": assignable.deadline,
            "description": assignable.description,
            "max_score": assignable.max_score,
            "created_at": assignable.created_at,
            "reference_file": {
                "file_url": assignable.file_url,
                "original_filename": assignable.original_filename
            } if assignable.file_url else None
        })
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching assignable: {str(e)}")

# this is to get all assignments for an assignable, done by profs
@app.get("/assignables/{assignable_id}/assignments")
async def get_assignable_assignments(
    assignable_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get all assignments for a assignable (professors only)"""
    try:
        if current_user["role"] == RoleType.STUDENT:
            raise HTTPException(status_code=403, detail="Only professors or TA can view all assignments")
        
        # Get the assignable
        assignable = db.query(Assignable).filter(Assignable.id == assignable_id).first()
        if not assignable:
            raise HTTPException(status_code=404, detail="Assignable not found")
        
        assignments = db.query(Assignment).filter(Assignment.assignable_id == assignable_id).all()
        
        result = []
        for assignment in assignments:
            assignment_data = {
                "id": assignment.id,
                "user_id": assignment.user_id,
                "submitted_on": assignment.submitted_on,
                "score": assignment.score,
                "max_score": assignable.max_score,
                "file": {
                    "file_url": assignment.file_url,
                    "original_filename": assignment.original_filename
                },
                "user": {
                    "id": assignment.user.id,
                    "name": assignment.user.name,
                    "email": assignment.user.email
                } if assignment.user else None
            }
            result.append(assignment_data)
        
        return JSONResponse(status_code=200, content=result)
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching assignments: {str(e)}")

# this is to delete a assignable and all its assignments, done by profs
@app.delete("/assignables/{assignable_id}")
async def delete_assignable(
    assignable_id: int,
    db: Session = Depends(get_db),
    token: str = Depends(prof_or_ta_required)
):
    """Delete a assignable and all its assignments (professors only)"""
    try:
        assignable = db.query(Assignable).filter(Assignable.id == assignable_id).first()
        if not assignable:
            raise HTTPException(status_code=404, detail="Assignable not found")
        
        # Delete the reference file if it exists
        if assignable.file_url:
            local_path = assignable.file_url.lstrip('/')
            if os.path.exists(local_path):
                os.remove(local_path)
        
        # Delete all submission files
        assignments = db.query(Assignment).filter(Assignment.assignable_id == assignable_id).all()
        for assignment in assignments:
            if assignment.file_url:
                local_path = assignment.file_url.lstrip('/')
                if os.path.exists(local_path):
                    os.remove(local_path)
        
        # Delete all submissions
        db.query(Assignment).filter(Assignment.assignable_id == assignable_id).delete()
        
        # Delete the submittable
        db.delete(assignable)
        db.commit()
        
        return JSONResponse(status_code=200, content={"message": "Assignable deleted successfully"})
    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error deleting assignable: {str(e)}")
    
# this is to update a assignable, done by profs
@app.put("/assignables/{assignable_id}")
async def update_assignable(
    assignable_id: int,
    title: str = FastAPIForm(...),
    deadline: str = FastAPIForm(...),
    description: str = FastAPIForm(...),
    opens_at: Optional[str] = FastAPIForm(None),
    file: Optional[UploadFile] = None,
    db: Session = Depends(get_db),
    token: str = Depends(prof_or_ta_required)
):
    """Update a assignable (professors only)"""
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
            
            
        existing_assignable = db.query(Assignable).filter(Assignable.id == assignable_id).first()
        if not existing_assignable:
            raise HTTPException(status_code=404, detail="Assignable not found")
        
        # Update basic information
        existing_assignable.title = title
        existing_assignable.opens_at = opens_at
        existing_assignable.deadline = deadline
        existing_assignable.description = description
        
        # Handle file update if provided
        if file:
            # Delete old file if it exists
            if existing_assignable.file_url:
                old_file_path = existing_assignable.file_url.lstrip('/')
                if os.path.exists(old_file_path):
                    os.remove(old_file_path)
            
            # Save new file
            file_extension = file.filename.split('.')[-1]
            file_name = f"ref_{uuid.uuid4()}.{file_extension}"
            file_path = f"uploads/{file_name}"
            
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            
            existing_assignable.file_url = f"uploads/{file_name}"
            existing_assignable.original_filename = file.filename
        
        db.commit()
        db.refresh(existing_assignable)
        
        return JSONResponse(status_code=200, content={
            "message": "Submittable updated successfully",
            "submittable_id": existing_assignable.id
        })
    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)  # Clean up file if something went wrong
        raise HTTPException(status_code=500, detail=f"Error updating assignable: {str(e)}")
    
# this is to delete a assignment, done by profs or the student who submitted        
@app.delete("/assignments/{assignment_id}")
async def delete_assignment(
    assignment_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Delete a submission (professors or the submitting student)"""
    try:
        assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
        if not assignment:
            raise HTTPException(status_code=404, detail="Assignment not found")
        
        # Check if user is professor or the student who submitted
        user = current_user["user"]
        if current_user["role"] == RoleType.STUDENT:
            # For students, check if they belong to the team that submitted
            if user.id != assignment.user_id:
                raise HTTPException(status_code=403, detail="You can only delete your own submissions")
        
        # Delete the submission file if it exists
        if assignment.file_url:
            local_path = assignment.file_url.lstrip('/')
            if os.path.exists(local_path):
                os.remove(local_path)
        
        # Delete the submission record
        db.delete(assignment)
        db.commit()
        
        return JSONResponse(status_code=200, content={"message": "Assignment deleted successfully"})
    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error deleting assignment: {str(e)}")
    
# this is to grade a assignment, done by profs
@app.put("/assignments/{assignment_id}/grade")
async def grade_assignment(
    assignment_id: int,
    score: int = FastAPIForm(...),
    db: Session = Depends(get_db),
    token: str = Depends(prof_or_ta_required)
):
    """Grade a submission (professors only)"""
    try:
        # Get the submission
        assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
        if not assignment:
            raise HTTPException(status_code=404, detail="Assignment not found")
        
        # Get the submittable to check max score
        assignable = db.query(Assignable).filter(Assignable.id == assignment.assignable_id).first()
        if not assignable:
            raise HTTPException(status_code=404, detail="Assignable not found")
        
        # Validate score
        if score < 0:
            raise HTTPException(status_code=400, detail="Score cannot be negative")
        if score > assignable.max_score:
            raise HTTPException(
                status_code=400, 
                detail=f"Score cannot exceed maximum score of {assignable.max_score}"
            )
        
        # Update the submission score
        assignment.score = score
        db.commit()
        
        return JSONResponse(status_code=200, content={
            "message": "Submission graded successfully",
            "assignment_id": assignment.id,
            "score": assignment.score,
            "max_score": assignable.max_score
        })
    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error grading assignment: {str(e)}")

class UpdateTAsRequest(BaseModel):
    ta_ids: List[int]

@app.post("/teams/{team_id}/update-tas")
async def update_team_tas(
    team_id: int,
    request: UpdateTAsRequest,
    db: Session = Depends(get_db),
    token: str = Depends(prof_or_ta_required)
):
    """Update TA assignments for a specific team"""
    try:
        # Verify team exists
        team = db.query(Team).filter(Team.id == team_id).first()
        if not team:
            raise HTTPException(status_code=404, detail="Team not found")

        # Verify all TAs exist and are actually TAs
        tas = db.query(User).filter(
            User.id.in_(request.ta_ids),
            User.role_id == 3  # role_id 3 is for TAs
        ).all()

        if len(tas) != len(request.ta_ids):
            raise HTTPException(
                status_code=400,
                detail="One or more selected users are not TAs or do not exist"
            )

        # Delete existing TA assignments for this team
        db.query(Team_TA).filter(Team_TA.team_id == team_id).delete()

        # Create new TA assignments
        for ta_id in request.ta_ids:
            new_assignment = Team_TA(
                team_id=team_id,
                ta_id=ta_id
            )
            db.add(new_assignment)

        db.commit()
        return {"message": "TA assignments updated successfully"}

    except HTTPException as he:
        db.rollback()
        raise he
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error updating TA assignments: {str(e)}"
        )

@app.get("/api/users/me")
async def get_user_data(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """
    Fetch user data using the token.
    """
    try:
        # Decode the token to get the username
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if not username:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )
        
        # Fetch the user from the database
        user = db.query(User).filter(User.username == username).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Fetch the user's role
        role = db.query(Role).filter(Role.id == user.role_id).first()
        
        # Fetch the user's team name
        team_name = None
        if user.team_id:
            team = db.query(Team).filter(Team.id == user.team_id).first()
            team_name = team.name if team else None
        
        # Return user data
        return {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "username": user.username,
            "role": role.role.value,
            "team_name": team_name  # Send team name instead of team ID
        }
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired"
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching user data: {str(e)}"
        )

@app.get("/teams/get-invites")
async def get_invites(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user = current_user["user"]

    # Check if user is a student
    if current_user["role"] != RoleType.STUDENT:
        raise HTTPException(status_code=403, detail="Only students can view invites")

    # Check if he is already in a team    
    if user.teams:
        raise HTTPException(status_code=400, detail="You are already in a team")

    invites = user.invites
    # invites = db.query(TeamInvites).filter(TeamInvites.user_id == user.id).all()
    invite_data = []
    for team in invites:
        data = {}
        data["team_id"] = team.id
        data["team_name"] = team.name
        data["team_members"] = [member.name for member in team.members]
        invite_data.append(data)

    return {"invites": invite_data}

@app.post("/teams/invite")
async def invite_to_team(
    invite: InviteUserModel,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        # First check if team phase is enabled
        config = db.query(CourseConfig).first()
        if not config or not config.team_phase_enabled:
            raise HTTPException(
                status_code=403,
                detail="Team phase is currently disabled. You cannot invite users to teams at this time."
            )

        invited_user_id = int(invite.user_id)  # Update to use invite.user_id
        user = current_user["user"]

        # Ensure user is a student
        if current_user["role"] != RoleType.STUDENT:
            raise HTTPException(status_code=403, detail="Only students can join teams")

        if not user.teams:
            raise HTTPException(status_code=400, detail="You are not in a team")
        
        # Additional logic for inviting to a team goes here
        # ...
        # For example, you might want to check if the user is a team leader or has permission to invite others

        # TODO: Check if the user is a team leader and implement team leader and stuff

        # Check if the invited user exists
        invited_user = db.query(User).filter(User.id == invited_user_id).first()
        if not invited_user:
            raise HTTPException(status_code=404, detail="Invited user not found")
        
        # Check if invited user is in a team
        if invited_user.team_id or invited_user.teams:
            raise HTTPException(status_code=400, detail="Invited user is already in a team")
        
        team = user.teams[0]
        # Check if the team already has an invite for the user
        if invited_user in team.invites:
            raise HTTPException(status_code=400, detail="User already invited to this team")

        team.invites.append(invited_user)  # Assuming the relationship is set up correctly
        db.commit()
        return {"detail": "User invited to team successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}") # TODO: Do I need to change this
    
@app.get("/teams/outgoing-invites")
async def get_outgoing_invites(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        user = current_user["user"]

        # Ensure user is a student
        if current_user["role"] != RoleType.STUDENT:
            raise HTTPException(status_code=403, detail="Only students can view outgoing invites")

        if not user.teams or not user.team_id:
            raise HTTPException(status_code=400, detail="You are not in a team")
        
        team = user.teams[0]
        # Fetch outgoing invites for the user's team
        outgoing_invites = team.invites  # Assuming the relationship is set up correctly
        
        invite_data = {}
        invite_data["team_id"] = user.team_id
        invite_data["team_name"] = team.name
        invite_data["data"] = []
        for invite in outgoing_invites:
            data = {}
            data["invited_user_id"] = invite.user_id
            data["invited_user_name"] = invite.name
            invite_data["data"].append(data)

        return {"outgoing_invites": invite_data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}") # TODO: Do I need to change this


@app.post("/teams/join")
async def join_team(
    invite: JoinTeamModel,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # First check if team phase is enabled
    config = db.query(CourseConfig).first()
    if not config or not config.team_phase_enabled:
        raise HTTPException(
            status_code=403,
            detail="Team phase is currently disabled. You cannot join teams at this time."
        )

    invite_team_id = int(invite.team_id)  # Update to use invite.team_id
    user = current_user["user"]
    # Check if user is a student
    if current_user["role"] != RoleType.STUDENT:
        raise HTTPException(status_code=403, detail="Only students can join teams")
    
    # Check if he is already in a team
    if user.teams:
        raise HTTPException(status_code=400, detail="You already belong to a team!")
    
    # Check if team invite exists
    
    for team in user.invites:
        if team.id == invite_team_id:
            team_id = team.id
            break
    else:
        raise HTTPException(status_code=404, detail="Invite not found")

    
    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found. It might have been deleted")

    user.team_id = team.id
    team.members.append(user)
    db.commit()
    db.refresh(team)

    return {"detail": "Successfully joined the team", "team_id": team.id, "team_name": team.name}

@app.post("/teams/create")
async def create_team(
    team: TeamCreateModel,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # First check if team phase is enabled
    config = db.query(CourseConfig).first()
    if not config or not config.team_phase_enabled:
        raise HTTPException(
            status_code=403,
            detail="Team phase is currently disabled. You cannot create teams at this time."
        )
    
    team_name = team.name
    user = current_user["user"]
    # Check if user is a student
    if current_user["role"] != RoleType.STUDENT:
        raise HTTPException(status_code=403, detail="Only students can create teams")
    # Check if user has an existing team

    if user.teams:
        raise HTTPException(status_code=400, detail="You already belong to a team!")
    
    # Check if team name is already taken
    existing_team = db.query(Team).filter(Team.name == team_name).first()
    if existing_team:
        raise HTTPException(status_code=400, detail="Team name already taken")
    
    # Create new team
    new_team = Team(
        name=team_name
    )
    db.add(new_team)
    db.commit()
    db.refresh(new_team)
    # Add user to the team
    user.team_id = new_team.id
    new_team.members.append(user)

    db.commit()
    db.refresh(new_team)

    return {"team_id": new_team.id, "team_name": new_team.name, "members": [member.name for member in new_team.members]}


@app.put("/api/users/skills")  # Changed from POST to PUT and updated endpoint path
async def update_user_skills(
    request: dict,  # Changed to accept request body as dict
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update skills for the currently logged in TA"""
    try:
        user = current_user["user"]
        
        # Check if user is a TA
        if current_user["role"] != RoleType.TA:
            raise HTTPException(
                status_code=403,
                detail="Only TAs can update their skills"
            )
        
        # Get skill_ids from request body
        skill_ids = request.get("skill_ids", [])
        if not isinstance(skill_ids, list):
            raise HTTPException(
                status_code=400,
                detail="skill_ids must be a list of integers"
            )
        
        # Get all skills by IDs
        skills = db.query(Skill).filter(Skill.id.in_(skill_ids)).all()
        if len(skills) != len(skill_ids):
            raise HTTPException(
                status_code=400, 
                detail="Some skill IDs are invalid"
            )
        
        # Clear existing skills and assign new ones
        user.skills = skills
        db.commit()
        
        # Format response
        updated_skills = []
        for skill in skills:
            updated_skills.append({
                "id": skill.id,
                "name": skill.name,
                "bgColor": skill.bgColor,
                "color": skill.color,
                "icon": skill.icon
            })
        
        return JSONResponse(
            status_code=200,
            content=updated_skills  # Return just the skills array to match frontend expectation
        )
    
    except HTTPException as he:
        db.rollback()
        raise he
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error updating skills: {str(e)}"
        )

@app.get("/api/skills")
async def get_all_available_skills(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all available skills from the database"""
    try:
        # Only TAs can access skills
        if current_user["role"] != RoleType.TA:
            raise HTTPException(
                status_code=403,
                detail="Only TAs can view and manage skills"
            )

        # Query all skills from the database
        skills = db.query(Skill).all()
        
        # Format the response
        formatted_skills = []
        for skill in skills:
            formatted_skills.append({
                "id": skill.id,
                "name": skill.name,
                "bgColor": skill.bgColor,
                "color": skill.color,
                "icon": skill.icon
            })

        return JSONResponse(status_code=200, content=formatted_skills)

    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching skills: {str(e)}"
        )

@app.get("/api/users/skills")
async def get_user_skills(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get currently logged-in TA's skills"""
    try:
        user = current_user["user"]
        
        # Check if user is a TA
        if current_user["role"] != RoleType.TA:
            raise HTTPException(
                status_code=403,
                detail="Only TAs can view their skills"
            )

        # Get user's current skills
        skills = user.skills
        
        # Format the response
        formatted_skills = []
        for skill in skills:
            formatted_skills.append({
                "id": skill.id,
                "name": skill.name,
                "bgColor": skill.bgColor,
                "color": skill.color,
                "icon": skill.icon
            })

        return JSONResponse(status_code=200, content=formatted_skills)

    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching user skills: {str(e)}"
        )

@app.get("/tas", response_model=List[dict])
async def get_all_tas(db: Session = Depends(get_db)):
    """
    Get all TAs with their skills from the database
    """
    try:
        # Get all users with role_id = 3 (TAs)
        ta_role_id = 3  # Assuming 3 is the role_id for TAs
        tas = db.query(User).filter(User.role_id == ta_role_id).all()
        
        result = []
        for ta in tas:
            # Get skills for this TA
            skills = []
            for skill in ta.skills:
                skills.append({
                    "id": skill.id,
                    "name": skill.name,
                    "bgColor": skill.bgColor,
                    "color": skill.color,
                    "icon": skill.icon
                })
            
            # Add TA with their skills to result
            result.append({
                "id": ta.id,
                "name": ta.name,
                "email": ta.email,
                "skills": skills
            })
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching TAs: {str(e)}")


# Schema for update requests
class ConfigUpdateRequest(BaseModel):
    enabled: bool

# GET routes to check configuration status
@app.get("/config/team-phase")
async def get_team_phase_status(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    config = db.query(CourseConfig).first()
    if not config:
        config = CourseConfig(
            team_phase_enabled=True,
            discussions_enabled=True,
            feedback_enabled=True,
            updated_by=1  # Default admin/prof ID
        )
        db.add(config)
        db.commit()
    return {"enabled": config.team_phase_enabled}

@app.get("/config/discussions")
async def get_discussions_status(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):  
    config = db.query(CourseConfig).first()
    if not config:
        config = CourseConfig(
            team_phase_enabled=True,
            discussions_enabled=True,
            feedback_enabled=True,
            updated_by=1
        )
        db.add(config)
        db.commit()
    return {"enabled": config.discussions_enabled}

@app.get("/config/feedback")
async def get_feedback_status(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
): 
    config = db.query(CourseConfig).first()
    if not config:
        config = CourseConfig(
            team_phase_enabled=True,
            discussions_enabled=True,
            feedback_enabled=True,
            updated_by=1
        )
        db.add(config)
        db.commit()
    return {"enabled": config.feedback_enabled}

# PUT routes to update configurations (professor only)
@app.put("/config/team-phase")
async def update_team_phase_status(
    request: ConfigUpdateRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user["role"] != RoleType.PROF:
        raise HTTPException(status_code=403, detail="Only professors can update course configurations")
    
    config = db.query(CourseConfig).first()
    if not config:
        config = CourseConfig(
            team_phase_enabled=request.enabled,
            discussions_enabled=True,
            feedback_enabled=True,
            updated_by=current_user["user"].id
        )
        db.add(config)
    else:
        config.team_phase_enabled = request.enabled
        config.updated_by = current_user["user"].id
    
    db.commit()
    return {"enabled": config.team_phase_enabled}

@app.put("/config/discussions")
async def update_discussions_status(
    request: ConfigUpdateRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user["role"] != RoleType.PROF:
        raise HTTPException(status_code=403, detail="Only professors can update course configurations")
    
    config = db.query(CourseConfig).first()
    if not config:
        config = CourseConfig(
            team_phase_enabled=True,
            discussions_enabled=request.enabled,
            feedback_enabled=True,
            updated_by=current_user["user"].id
        )
        db.add(config)
    else:
        config.discussions_enabled = request.enabled
        config.updated_by = current_user["user"].id
    
    db.commit()
    return {"enabled": config.discussions_enabled}

@app.put("/config/feedback")
async def update_feedback_status(
    request: ConfigUpdateRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user["role"] != RoleType.PROF:
        raise HTTPException(status_code=403, detail="Only professors can update course configurations")
    
    config = db.query(CourseConfig).first()
    if not config:
        config = CourseConfig(
            team_phase_enabled=True,
            discussions_enabled=True,
            feedback_enabled=request.enabled,
            updated_by=current_user["user"].id
        )
        db.add(config)
    else:
        config.feedback_enabled = request.enabled
        config.updated_by = current_user["user"].id
    
    db.commit()
    return {"enabled": config.feedback_enabled}
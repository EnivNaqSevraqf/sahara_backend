from fastapi import FastAPI, Depends, HTTPException, status, WebSocket, File, UploadFile, Form as FastAPIForm
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session, relationship, sessionmaker
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta, timezone
from enum import Enum
from pydantic import BaseModel, EmailStr, validator
from .models.user import User, Prof, Student, TA
from .models.user_otp import UserOTP
from .models.assignable import Assignable
from .models.assignment import Assignment
from .models.roles import Role, RoleType
from .models.team import Team
from .models.form import Form
from .models.channel import Channel
from .models.message import Message
from .models.feedback_submission import FeedbackSubmission
from .models.feedback_detail import FeedbackDetail
from .models.submittable import Submittable
from .models.submission import Submission
from .models.announcement import Announcement
from .models.form_response import FormResponse
from .models.gradeables import Gradeable
from .models.skills import Skill
from .models.gradeable_scores import GradeableScores
from .models.global_calendar_event import GlobalCalendarEvent
from .models.global_calendar_event import NewGlobalCalendarEvent
from .models.user_calendar_event import NewUserCalendarEvent
from .models.user_calendar_event import UserCalendarEvent
from .models.team_calendar_event import TeamCalendarEvent
from .models.team_calendar_event import NewTeamCalendarEvent
from .models.team_ta import Team_TA

from .schemas.auth_schemas import (
    QueryBaseModel, UserBase, LoginRequest, ResetPasswordRequest,
    CreateProfRequest, TempRegisterRequest, RequestOTPModel,
    VerifyOTPModel, ResetPasswordWithOTPModel, UserIdRequest
)
from .schemas.form_schemas import FormCreateRequest, FormResponseSubmit
from .schemas.gradeable_schemas import GradeableCreateRequest
from .schemas.team_schemas import (
    TeamNameUpdateRequest, TABase, TeamBase, TADisplay,
    TeamDisplay, AllocationResponse, UpdateTAsRequest
)
from .schemas.announcement_schemas import Announcements, Show
from .schemas.calendar_schemas import CalendarUpdateModel
from .schemas.feedback_schemas import FeedbackDetailRequest, FeedbackSubmissionRequest
from .schemas.discussion_schemas import MessageModel
from .schemas.auth_schemas import UserBase, BaseModel
from .schemas.skill_schemas import (
    SkillRequest, SkillBase, SkillCreate, SkillResponse,
    AssignSkillsRequest, AssignTeamSkillsRequest
)
from .database.db import Base
from .dependencies.get_db import get_db
from .dependencies.auth import prof_or_ta_required, prof_required, get_current_user, get_verified_user, validate_channel_access
from .database.init import create_default_roles, create_default_admin
from .config.config import engine
from .routers import (
    api_submissions, api_users, api_teams, api_skills, 
    api_gradeables, api_assignables, api_submittables,
    api_discussions, api_assignments, api_otp, api_feedback,
    api_people, api_calendar, api_match, api_forms,
    api_quiz, api_announcements, api_auth, api_files
)

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

create_default_roles()
create_default_admin()

# Include all routers
app.include_router(api_submissions.router)
app.include_router(api_users.router)
app.include_router(api_teams.router)
app.include_router(api_skills.router)
app.include_router(api_gradeables.router)
app.include_router(api_assignables.router)
app.include_router(api_submittables.router)
app.include_router(api_discussions.router)
app.include_router(api_assignments.router)
app.include_router(api_otp.router)
app.include_router(api_feedback.router)
app.include_router(api_people.router)
app.include_router(api_calendar.router)
app.include_router(api_match.router)
app.include_router(api_forms.router)
# app.include_router(api_quiz.router)
app.include_router(api_announcements.router)
app.include_router(api_auth.router)
app.include_router(api_files.router)

@app.get("/")
async def root():
    return {"message": "Welcome to Sahara Backend API"}

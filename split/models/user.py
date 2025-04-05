from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship, validates
from ..database.db import Base
from .associations import user_skills, team_members, invites
from ..config.config import SessionLocal
from ..models.roles import RoleType, Role
from .form_response import FormResponse

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


class Prof(Base):
    __tablename__ = "profs"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    email = Column(String, unique=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)

class Student(Base):
    __tablename__ = "students"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    email = Column(String, unique=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)

class TA(Base):
    __tablename__ = "tas"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    email = Column(String, unique=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
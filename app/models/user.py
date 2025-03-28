from sqlalchemy import Column, Integer, String, ForeignKey, Enum
from sqlalchemy.orm import relationship
import enum
from app.db.base import Base
from app.models.team import team_members

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
    username = Column(String, nullable=False, unique=True)
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=False)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=True)
    hashed_password = Column(String, nullable=False)

    role = relationship("Role", back_populates="users")
    teams = relationship("Team", secondary=team_members, back_populates="members")
    responses = relationship("FormResponse", back_populates="user")
    gradeables = relationship("Gradeable", back_populates="creator")
    calendar_events = relationship("UserCalendarEvent", back_populates="creator")
    team_calendar_events = relationship("TeamCalendarEvent", back_populates="creator")
    skills = relationship("Skill", secondary="user_skills", back_populates="users")
    gradeable_scores = relationship("GradeableScores", back_populates="user")
    submittables = relationship("Submittable", back_populates="creator")
    messages = relationship("Message", back_populates="sender")
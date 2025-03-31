from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship, validates
from ..database.db import Base
from .skills import user_skills
from ..config.config import SessionLocal
from ..models.roles import RoleType, Role

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
    assignables = relationship("Assignable", back_populates="creator", lazy="joined")
    assignments = relationship("Assignment", back_populates="user")
    messages = relationship("Message", back_populates="sender")
    

    @validates('skills')
    def validate_skills(self, key, skill):
        # Only allow TAs to have skills
        with SessionLocal() as db:
            role = db.query(Role).filter_by(id=self.role_id).first()
            if role and role.role != RoleType.TA:
                raise ValueError("Only TAs can have skills.")
        return skill


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
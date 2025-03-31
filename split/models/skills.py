from sqlalchemy import Column, Integer, String, Float, ForeignKey, Enum, Table
from ..database.db import Base
from sqlalchemy.orm import relationship
from enum import Enum as PyEnum

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
class TeamSkill(Base):
    __tablename__ = "team_skills"

class UserSkill(Base):
    __tablename__ = "user_skills"
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

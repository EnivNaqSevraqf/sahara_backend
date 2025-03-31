from sqlalchemy import Column, Integer, String, Float, ForeignKey, Enum
from ..database.db import Base
from sqlalchemy.orm import relationship
from enum import Enum as PyEnum
from .associations import user_skills, team_skills

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

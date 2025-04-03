from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from ..database.db import Base
from .associations import team_skills, team_members

class Team(Base):
    __tablename__ = "teams"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    
    members = relationship("User", secondary=team_members, back_populates="teams")
    skills = relationship("Skill", secondary=team_skills, back_populates="teams")
    submissions = relationship("Submission", back_populates="team") 
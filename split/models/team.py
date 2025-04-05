from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from ..database.db import Base
from .associations import team_skills, team_members, invites

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
    #
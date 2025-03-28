from sqlalchemy import Column, Integer, String, ForeignKey, Table
from sqlalchemy.orm import relationship
from app.db.base import Base

# Association tables
team_members = Table(
    "team_members", Base.metadata,
    Column("team_id", Integer, ForeignKey("teams.id"), primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id"), primary_key=True)
)

team_skills = Table(
    "team_skills", Base.metadata,
    Column("team_id", Integer, ForeignKey("teams.id"), primary_key=True),
    Column("skill_id", Integer, ForeignKey("skills.id"), primary_key=True)
)

class Team(Base):
    __tablename__ = "teams"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    
    members = relationship("User", secondary=team_members, back_populates="teams")
    skills = relationship("Skill", secondary=team_skills, back_populates="teams")
    submissions = relationship("Submission", back_populates="team")

class Team_TA(Base):
    __tablename__ = "team_tas"
    id = Column(Integer, primary_key=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    ta_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    team = relationship("Team", backref="team_tas")
    ta = relationship("User", backref="ta_teams")
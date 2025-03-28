from sqlalchemy import Column, Integer, String, ForeignKey, Float, DateTime, ARRAY, Text
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.db.base import Base

class Submission(Base):
    __tablename__ = "submissions"
    
    id = Column(Integer, primary_key=True)
    assignment_id = Column(Integer, nullable=False)
    team_id = Column(Integer, ForeignKey("teams.id"))
    submitted_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    files = Column(ARRAY(String))
    grade = Column(Float, nullable=True)
    feedback = Column(Text, nullable=True)
    graded_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    graded_at = Column(DateTime, nullable=True)

    team = relationship("Team", back_populates="submissions")
    grader = relationship("User", foreign_keys=[graded_by])
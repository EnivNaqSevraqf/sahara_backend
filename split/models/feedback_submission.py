from sqlalchemy import Column, Integer, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from ..database.db import Base  # Import the shared Base

class FeedbackSubmission(Base):
    __tablename__ = "feedback_submissions"
    id = Column(Integer, primary_key=True)
    submitter_id = Column(Integer, ForeignKey("users.id"))
    team_id = Column(Integer, ForeignKey("teams.id"))
    submitted_at = Column(DateTime, default=datetime.now(timezone.utc))
    
    # Define relationships properly with string references to avoid circular imports
    submitter = relationship("User", foreign_keys=[submitter_id], back_populates="feedback_submissions")
    team = relationship("Team", back_populates="feedback_submissions")
    details = relationship("FeedbackDetail", back_populates="submission")
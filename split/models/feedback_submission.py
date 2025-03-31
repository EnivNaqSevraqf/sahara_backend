from sqlalchemy import Column, Integer, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class FeedbackSubmission(Base):
    __tablename__ = "feedback_submissions"
    id = Column(Integer, primary_key=True)
    submitter_id = Column(Integer, ForeignKey("users.id"))
    team_id = Column(Integer, ForeignKey("teams.id"))
    submitted_at = Column(DateTime, default=datetime.now(timezone.utc))
    submitter = relationship("User", foreign_keys=[submitter_id])
    team = relationship("Team")
    details = relationship("FeedbackDetail", back_populates="submission") 
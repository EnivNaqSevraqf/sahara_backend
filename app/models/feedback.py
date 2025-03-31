from sqlalchemy import Column, Integer, ForeignKey, Float, Text, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.db.base import Base

class FeedbackSubmission(Base):
    __tablename__ = "feedback_submissions"
    id = Column(Integer, primary_key=True)
    submitter_id = Column(Integer, ForeignKey("users.id"))
    team_id = Column(Integer, ForeignKey("teams.id"))
    submitted_at = Column(DateTime, default=datetime.now(timezone.utc))
    submitter = relationship("User", foreign_keys=[submitter_id])
    team = relationship("Team")
    details = relationship("FeedbackDetail", back_populates="submission")

class FeedbackDetail(Base):
    __tablename__ = "feedback_details"
    id = Column(Integer, primary_key=True)
    submission_id = Column(Integer, ForeignKey("feedback_submissions.id"))
    member_id = Column(Integer, ForeignKey("users.id"))
    contribution = Column(Float)
    remarks = Column(Text)
    submission = relationship("FeedbackSubmission", back_populates="details")
    member = relationship("User", foreign_keys=[member_id])
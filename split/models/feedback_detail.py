from sqlalchemy import Column, Integer, ForeignKey, Float, Text
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class FeedbackDetail(Base):
    __tablename__ = "feedback_details"
    id = Column(Integer, primary_key=True)
    submission_id = Column(Integer, ForeignKey("feedback_submissions.id"))
    member_id = Column(Integer, ForeignKey("users.id"))
    contribution = Column(Float)
    remarks = Column(Text)
    submission = relationship("FeedbackSubmission", back_populates="details")
    member = relationship("User", foreign_keys=[member_id]) 
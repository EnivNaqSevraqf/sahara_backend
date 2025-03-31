from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class Assignment(Base):
    __tablename__ = "assignments"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    submitted_on = Column(String, default=datetime.now(timezone.utc).isoformat())
    file_url = Column(String, nullable=False)  # URL path to the reference file
    original_filename = Column(String, nullable=False)
    assignable_id = Column(Integer, ForeignKey("assignables.id"), nullable=False)
    score = Column(Integer, nullable=True)  # Score received for this submission

    user = relationship("User", back_populates="assignments")
    assignable = relationship("Assignable", back_populates="assignments") 
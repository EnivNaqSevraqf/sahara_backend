from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from ..database.db import Base

class Submission(Base):
    __tablename__ = "submissions"
    id = Column(Integer, primary_key=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    submitted_on = Column(String, default=datetime.now(timezone.utc).isoformat())
    file_url = Column(String, nullable=False)  # URL path to the reference file
    original_filename = Column(String, nullable=False)
    submittable_id = Column(Integer, ForeignKey("submittables.id"), nullable=False)
    score = Column(Integer, nullable=True)  # Score received for this submission

    team = relationship("Team", back_populates="submissions", lazy="joined")
    submittable = relationship("Submittable", back_populates="submissions", lazy="joined") 
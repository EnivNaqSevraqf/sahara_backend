from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship, validates
from datetime import datetime, timezone
from ..database.db import Base
from ..config.config import SessionLocal
from ..models.user import User
from ..models.roles import RoleType

class Submittable(Base):
    __tablename__ = "submittables"
    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)  # Adding title field
    opens_at = Column(String, nullable=True)  # ISO 8601 format
    deadline = Column(String, nullable=False)  # ISO 8601 format
    description = Column(String, nullable=False)
    file_url = Column(String, nullable=False)  # URL path to the reference file
    original_filename = Column(String, nullable=False)
    max_score = Column(Integer, nullable=False)  # Maximum possible score for this submittable
    created_at = Column(String, default=datetime.now(timezone.utc).isoformat())
    creator_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    creator = relationship("User", back_populates="submittables", lazy="joined")
    submissions = relationship("Submission", back_populates="submittable", lazy="joined")

    @validates("creator_id")
    def validate_creator(self, key, value):
        with SessionLocal() as db:
            user = db.query(User).filter_by(id=value).first()
            if user and user.role.role == RoleType.STUDENT:
                raise ValueError("Only professors or TAs can create submittables.")
        return value 
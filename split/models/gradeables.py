from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime
from sqlalchemy.orm import relationship, validates
from datetime import datetime, timezone
from ..database.db import Base
from ..config.config import SessionLocal
from ..models.user import User
from ..models.roles import RoleType


class Gradeable(Base):
    __tablename__ = "gradeables"
    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    #description = Column(String, nullable=True)
    #due_date = Column(String, nullable=False)
    max_points = Column(Integer, nullable=False)
    creator_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(String, default=datetime.now(timezone.utc).isoformat())

    creator = relationship("User", back_populates="gradeables")
    scores = relationship("GradeableScores", back_populates="gradeable")

    @validates("creator_id")
    def validate_creator(self, key, value):
        with SessionLocal() as session:
            user = session.query(User).filter_by(id=value).first()
            if user and user.role.role == RoleType.STUDENT:
                raise ValueError("Students cannot create gradeables.")
        return value


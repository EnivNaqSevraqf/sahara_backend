from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, JSON
from sqlalchemy.orm import relationship, validates
from datetime import datetime, timezone
from sqlalchemy.ext.declarative import declarative_base
from ..config.config import SessionLocal
from ..models.user import User
from ..models.roles import RoleType

Base = declarative_base()

class TeamCalendarEvent(Base):
    __tablename__ = "team_calendar_events"
    id = Column(Integer, primary_key=True)
    events = Column(JSON, nullable=False)
    description = Column(String, nullable=False)
    start_time = Column(String, nullable=False)
    end_time = Column(String, nullable=False)
    creator_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(String, default=datetime.now(timezone.utc).isoformat())

    creator = relationship("User", back_populates="team_calendar_events") 

    @validates("creator_id")
    def validate_creator(self, key, value):
        with SessionLocal() as session:
            user = session.query(User).filter_by(id=value).first()
            if user and user.role == RoleType.STUDENT:
                raise ValueError("Students cannot create calendar events.")
            return value
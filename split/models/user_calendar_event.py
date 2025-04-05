from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, JSON
from sqlalchemy.orm import relationship, validates
from datetime import datetime, timezone
from ..database.db import Base
from ..config.config import SessionLocal
from ..models.user import User
from ..models.roles import RoleType

class UserCalendarEvent(Base):
    __tablename__ = "user_calendar_events"
    id = Column(Integer, primary_key=True)
    events = Column(JSON, nullable=False)
    description = Column(String, nullable=False)
    start_time = Column(String, nullable=False)
    end_time = Column(String, nullable=False)
    creator_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
    created_at = Column(String, default=datetime.now(timezone.utc).isoformat())

    creator = relationship("User", back_populates="calendar_events", lazy="joined")

    @validates("creator_id")
    def validate_creator(self, key, value):
        with SessionLocal() as session:
            user = session.query(User).filter_by(id=value).first()
            if user and user.role.role == RoleType.STUDENT:
                raise ValueError("Students cannot create calendar events.")
        return value

class NewUserCalendarEvent(Base):
    __tablename__ = "user_calendar"
    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    subtitle = Column(String, nullable=True)
    start = Column(String, nullable=False)
    end = Column(String, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    user = relationship("User", back_populates="user_calendar_events", lazy="joined")

    # @validates("user_id")
    # def validate_user(self, key, value):
    #     with SessionLocal() as session:
    #         user = session.query(User).filter_by(id=value).first()
    #         if user and user.role.role != RoleType.STUDENT:
    #             raise ValueError("Only students can create personal calendar events.")
    #     return value
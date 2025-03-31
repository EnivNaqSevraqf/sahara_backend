from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, JSONB
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from ..database import Base

class GlobalCalendarEvent(Base):
    __tablename__ = "global_calendar_events"
    id = Column(Integer, primary_key=True)
    events = Column(JSONB, nullable=False)
    description = Column(String, nullable=False)
    start_time = Column(String, nullable=False)
    end_time = Column(String, nullable=False)
    created_at = Column(String, default=datetime.now(timezone.utc).isoformat())

class UserCalendarEvent(Base):
    __tablename__ = "user_calendar_events"
    id = Column(Integer, primary_key=True)
    events = Column(JSONB, nullable=False)
    description = Column(String, nullable=False)
    start_time = Column(String, nullable=False)
    end_time = Column(String, nullable=False)
    creator_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
    created_at = Column(String, default=datetime.now(timezone.utc).isoformat())

    creator = relationship("User", back_populates="calendar_events")

class TeamCalendarEvent(Base):
    __tablename__ = "team_calendar_events"
    id = Column(Integer, primary_key=True)
    events = Column(JSONB, nullable=False)
    description = Column(String, nullable=False)
    start_time = Column(String, nullable=False)
    end_time = Column(String, nullable=False)
    creator_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(String, default=datetime.now(timezone.utc).isoformat())

    creator = relationship("User", back_populates="team_calendar_events")
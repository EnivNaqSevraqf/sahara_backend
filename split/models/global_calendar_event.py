from sqlalchemy import Column, Integer, String, DateTime, JSON
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from ..database.db import Base

class GlobalCalendarEvent(Base):
    __tablename__ = "global_calendar_events"
    id = Column(Integer, primary_key=True)
    events = Column(JSON, nullable=False)
    description = Column(String, nullable=False)
    start_time = Column(String, nullable=False)
    end_time = Column(String, nullable=False)
    created_at = Column(String, default=datetime.now(timezone.utc).isoformat())

class NewGlobalCalendarEvent(Base):
    __tablename__ = "global_calendar"
    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    subtitle = Column(String, nullable=True)
    start = Column(String, nullable=False)
    end = Column(String, nullable=False)

# print("GlobalCalendarEvent and NewGlobalCalendarEvent models defined successfully.")


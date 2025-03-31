from sqlalchemy import Column, Integer, String, DateTime, JSON
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class GlobalCalendarEvent(Base):
    __tablename__ = "global_calendar_events"
    id = Column(Integer, primary_key=True)
    events = Column(JSON, nullable=False)
    description = Column(String, nullable=False)
    start_time = Column(String, nullable=False)
    end_time = Column(String, nullable=False)
    created_at = Column(String, default=datetime.now(timezone.utc).isoformat()) 
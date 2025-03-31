from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship, validates
from datetime import datetime, timezone
from sqlalchemy.ext.declarative import declarative_base
from ..config.config import SessionLocal
from ..models.user import User
from ..models.roles import RoleType

Base = declarative_base()

class Announcement(Base):
    __tablename__ = "announcements"
    id = Column(Integer, primary_key=True)
    creator_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(String, default=datetime.now(timezone.utc).isoformat())
    title = Column(String, nullable=False)
    content = Column(String, nullable=False)  # Supports Markdown formatting for rich text
    url_name = Column(String, unique=True, nullable=True) 

    @validates("creator_id")
    def validate_creator(self, key, value):
        with SessionLocal() as session:
            user = session.query(User).filter_by(id=value).first()
            if user and user.role == RoleType.STUDENT:
                raise ValueError("Students cannot create announcements.")
            return value
from sqlalchemy import Column, Integer, String, DateTime, JSON
from sqlalchemy.orm import relationship, validates
from datetime import datetime, timezone
from ..database.db import Base
from ..config.config import SessionLocal
from ..models.roles import RoleType, Role

class Form(Base):
    __tablename__ = "forms"
    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    description = Column(String, nullable=True)
    created_at = Column(String, default=datetime.now(timezone.utc).isoformat())
    deadline = Column(String, nullable=False)  # ISO 8601 format
    form_json = Column(JSON, nullable=False)

    responses = relationship("FormResponse", back_populates="form", lazy="joined")

    @validates("target_type", "target_id")
    def validate_target(self, key, value):
        if self.target_type == RoleType.ROLE:
            with SessionLocal() as session:
                role = session.query(Role).filter_by(id=self.target_id).first()
                if role and role.name == RoleType.PROFESSOR:
                    raise ValueError("Forms cannot be assigned to Professors.")
        return value

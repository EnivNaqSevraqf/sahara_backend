from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class FormResponse(Base):
    __tablename__ = "form_responses"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    form_id = Column(Integer, ForeignKey("forms.id"), nullable=False)
    submitted_at = Column(String, default=datetime.now(timezone.utc).isoformat())
    response_data = Column(String, nullable=False)  # JSON or serialized response data

    user = relationship("User", back_populates="responses")
    form = relationship("Form", back_populates="responses") 
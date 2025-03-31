from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from ..database import Base

class UserOTP(Base):
    __tablename__ = "user_otps"
    
    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    hashed_otp = Column(String, nullable=False)
    expires_at = Column(String, nullable=False)  # ISO 8601 format
    
    # Relationship with User
    user = relationship("User", backref="otp_record") 
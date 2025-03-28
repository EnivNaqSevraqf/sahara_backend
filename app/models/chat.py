from sqlalchemy import Column, Integer, String, ForeignKey, Text, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from app.db.base import Base

class Channel(Base):
    __tablename__ = "channels"
    id = Column(Integer, primary_key=True)
    name = Column(String(50), nullable=False)
    type = Column(String(10), nullable=False)  # global, team, or ta-team
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=True)
    messages = relationship("Message", back_populates="channel")

class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True)
    content = Column(Text, nullable=False)
    sender_id = Column(Integer, ForeignKey("users.id"))
    channel_id = Column(Integer, ForeignKey("channels.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    message_type = Column(String(10), default='text')
    file_name = Column(String(255))

    sender = relationship("User", back_populates="messages")
    channel = relationship("Channel", back_populates="messages")
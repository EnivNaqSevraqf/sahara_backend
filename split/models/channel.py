from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from ..database import Base

class Channel(Base):
    __tablename__ = "channels"
    id = Column(Integer, primary_key=True)
    name = Column(String(50), nullable=False)
    type = Column(String(10), nullable=False)  # global, team, or ta-team
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=True)
    messages = relationship("Message", back_populates="channel") 
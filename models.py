from sqlalchemy import Column, Integer, String
from database import Base

class Announcements(Base):
    __tablename__ = 'announcements'
    id=Column(Integer, primary_key=True, index=True)
    title = Column(String)
    description = Column(String)
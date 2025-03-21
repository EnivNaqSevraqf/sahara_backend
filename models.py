from sqlalchemy import Column, Integer, String, JSON
from database import Base

class Announcements(Base):
    __tablename__ = 'announcements'
    id=Column(Integer, primary_key=True, index=True)
    title = Column(String)
    description = Column(JSON, nullable=True)
    file_path=Column(String, nullable=True)

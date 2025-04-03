from sqlalchemy import Column, Integer, String, Float, ForeignKey, Enum, Table
from sqlalchemy.orm import relationship
from ..database.db import Base
from enum import Enum as PyEnum

class RoleType(PyEnum):
    PROF = "prof"
    STUDENT = "student"
    TA = "ta"


class Role(Base):
    __tablename__ = "roles"
    id = Column(Integer, primary_key=True)
    role = Column(Enum(RoleType), nullable=False, unique=True)

    users = relationship("User", back_populates="role")
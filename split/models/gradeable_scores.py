from sqlalchemy import Column, Integer, ForeignKey
from sqlalchemy.orm import relationship
from ..database.db import Base

class GradeableScores(Base):
    __tablename__ = "gradeable_scores"
    id = Column(Integer, primary_key=True)
    gradeable_id = Column(Integer, ForeignKey("gradeables.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    score = Column(Integer, nullable=False)

    gradeable = relationship("Gradeable", back_populates="scores", lazy="joined")
    user = relationship("User", back_populates="gradeable_scores", lazy="joined") 
from sqlalchemy import Column, Integer, ForeignKey
from sqlalchemy.orm import relationship
from ..database import Base

class Team_TA(Base):
    __tablename__ = "team_tas"
    id = Column(Integer, primary_key=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    ta_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    team = relationship("Team", backref="team_tas")
    ta = relationship("User", backref="ta_teams") 
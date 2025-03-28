from pydantic import BaseModel
from typing import List

class TeamBase(BaseModel):
    team_name: str
    skills: List[str]

class TeamDisplay(TeamBase):
    id: int
    class Config:
        orm_mode = True

class TeamMember(BaseModel):
    id: int
    name: str
    is_current_user: bool

class TeamDetail(BaseModel):
    team_id: int
    team_name: str
    members: List[TeamMember]
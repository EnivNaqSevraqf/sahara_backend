from pydantic import BaseModel
from typing import List



class SkillRequest(BaseModel):
    name: str
    bgColor: str
    fgColor: str
    icon: str

class SkillBase(BaseModel):
    name: str
    bgColor: str
    color: str
    icon: str

class SkillCreate(SkillBase):
    pass

class SkillResponse(SkillBase):
    id: int

    class Config:
        orm_mode = True

class AssignSkillsRequest(BaseModel):
    user_id: int
    skill_ids: List[int]

class AssignTeamSkillsRequest(BaseModel):
    team_id: int
    skill_ids: List[int] 
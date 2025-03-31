from pydantic import BaseModel, validator
from typing import List

class TeamNameUpdateRequest(BaseModel):
    name: str

    @validator('name')
    def validate_name(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError('Team name cannot be empty')
        return v.strip()

class TABase(BaseModel):
    name: str
    skills: List[str]

class TeamBase(BaseModel):
    team_name: str
    skills: List[str]

class TADisplay(TABase):
    id: int

    class Config:
        orm_mode = True

class TeamDisplay(TeamBase):
    id: int

    class Config:
        orm_mode = True

class AllocationResponse(BaseModel):
    team_id: int
    required_skill_ids: List[int]
    assigned_ta_ids: List[int]


class UpdateTAsRequest(BaseModel):
    ta_ids: List[int]
from pydantic import BaseModel
from typing import Optional, Dict

class Announcements(BaseModel):
    title: str
    description: dict

class Show(BaseModel):
    id: int
    creator_id: int
    created_at: str
    title: str
    content: str  # Contains Markdown formatted text
    url_name: Optional[str] = None
    creator_name: Optional[str] = None

    class Config:
        orm_mode = True 
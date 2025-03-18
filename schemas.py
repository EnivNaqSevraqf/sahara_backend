from pydantic import BaseModel

class Announcements(BaseModel):
    title:str
    description:str

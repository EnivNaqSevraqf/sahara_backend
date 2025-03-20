from pydantic import BaseModel

class Announcements(BaseModel):
    title:str
    description:dict

class Show(Announcements):
    class Config():
        orm_mode=True
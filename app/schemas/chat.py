from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List, Dict, Any

class MessageBase(BaseModel):
    content: str
    message_type: str = "text"
    channel_id: int
    file_name: Optional[str] = None

class MessageCreate(MessageBase):
    pass

class MessageResponse(MessageBase):
    id: int
    sender_id: int
    sender_name: str
    created_at: datetime

    class Config:
        from_attributes = True

class ChannelBase(BaseModel):
    name: str
    type: str  # global, team, or ta-team
    team_id: Optional[int] = None

class ChannelCreate(ChannelBase):
    pass

class ChannelResponse(ChannelBase):
    id: int
    
    class Config:
        from_attributes = True
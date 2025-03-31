from pydantic import BaseModel
from typing import List, Any

class CalendarUpdateModel(BaseModel):
    events: List[Any]
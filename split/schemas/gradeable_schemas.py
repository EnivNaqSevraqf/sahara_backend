from pydantic import BaseModel
from typing import Optional

class GradeableCreateRequest(BaseModel):
    title: str
    max_points: int
# max_points: str = FastAPIForm(...)
    
    # @validator('due_date')
    # def validate_due_date(cls, v):
    #     try:
    #         # Validate ISO 8601 format
    #         datetime.fromisoformat(v.replace('Z', '+00:00'))
    #         return v
    #     except ValueError:
    #         raise ValueError("Invalid due date format. Use ISO 8601 (YYYY-MM-DDTHH:MM:SSZ)")
            
    # @validator('max_points')
    # def validate_max_points(cls, v):
    #     if v <= 0:
    #         raise ValueError("Maximum points must be greater than zero")
    #     return v

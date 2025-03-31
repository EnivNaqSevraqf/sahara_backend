from pydantic import BaseModel, validator
from typing import Dict, Any, Optional
from datetime import datetime

class FormCreateRequest(BaseModel):
    title: str
    form_json: Dict[str, Any]
    deadline: str

    @validator('deadline')
    def validate_deadline(cls, v):
        try:
            datetime.fromisoformat(v)
            return v
        except ValueError:
            raise ValueError('Invalid deadline format. Use ISO 8601 format.')

class FormResponseSubmit(BaseModel):
    form_id: int
    response_data: str  # JSON serialized response data


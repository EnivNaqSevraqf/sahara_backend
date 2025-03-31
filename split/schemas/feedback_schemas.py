from pydantic import BaseModel
from typing import List

class FeedbackDetailRequest(BaseModel):
    member_id: int
    contribution: float
    remarks: str

class FeedbackSubmissionRequest(BaseModel):
    team_id: int
    details: List[FeedbackDetailRequest] 
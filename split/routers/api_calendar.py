from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from ..database import get_db
from ..models.user import User
from ..schemas.calendar_schemas import CalendarUpdateModel
from fastapi.responses import JSONResponse
from typing import List, Any
from pydantic import BaseModel
from ..crud.calendar import get_global_events, overwrite_global_events

router = APIRouter(
    prefix="/calendar",
    tags=["Calendar"]
)

class CalendarUpdateModel(BaseModel):
    events: List[Any]
    # token: str = Header(None)

@router.post("/update")
def update_calendar(
    calendar_update_model: CalendarUpdateModel,
    db: Session = Depends(get_db),
    # user_id: int = Depends(resolve_token)
):
    # user = db.query(User).filter_by(id=user_id).first()
    print(calendar_update_model.events)
    global_events = calendar_update_model.events
    # global_events, personal_events, team_events = split_events(calendar_update_model.events)
    print(global_events)
    overwrite_global_events(global_events, db)
    return {"message": "Calendar updated"}
    # if user.role == RoleType.PROF:
    #     overwrite_global_events(events, db)
    # elif user.role == RoleType.STUDENT:
    #     overwrite_personal_events(user, events, db)
    # elif user.role == RoleType.TA:
    #     overwrite_team_events(user, events, db)
    # return {"message": "Calendar updated"}
    # if the role is admin
    # select all the global events

    # overwrite_global_events



    
    pass

@router.get("/")
def get_calendar(
    db: Session = Depends(get_db),
    # user_id: int = Depends(resolve_token)
):
    # Get the global events
    global_events = get_global_events(db)
    print(global_events)
    return JSONResponse(status_code=201, content=global_events)
    # return {"message": "Calendar retrieved", "events": global_events}
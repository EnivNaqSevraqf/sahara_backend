from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from split.models.team_calendar_event import NewTeamCalendarEvent
from ..database.db import get_db
from ..models.user import User
from ..schemas.calendar_schemas import CalendarUpdateModel
from fastapi.responses import JSONResponse
from typing import List, Any
from pydantic import BaseModel
from ..models.roles import RoleType
from ..dependencies.auth import get_current_user
from ..crud.calendar import get_global_events, overwrite_global_events
from ..models.global_calendar_event import NewGlobalCalendarEvent
from ..models.user_calendar_event import NewUserCalendarEvent
router = APIRouter(
    prefix="/calendar",
    tags=["Calendar"]
)

class CalendarEvent(BaseModel):
    start: str
    end: str
    title: str
    subtitle: str
    type: str
    # color: str = None
    # allDay: bool = False

class CalendarUpdateModel(BaseModel):
    events: List[CalendarEvent]
    # token: str = Header(None)

@router.post("/create")
def create_calendar(
    calendar_event: CalendarEvent,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    # user_id: int = Depends(resolve_token)
):
    
    user = current_user["user"]
    role = current_user["role"]

    if calendar_event.type == "global":
        # Check if the user is professor
        if role != RoleType.PROF:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to create global events")
        # Create the global event
        new_event = NewGlobalCalendarEvent(
            title=calendar_event.title,
            subtitle=calendar_event.subtitle,
            start=calendar_event.start,
            end=calendar_event.end
        )

        db.add(new_event)
        db.commit()
        db.refresh(new_event)

        event_json = {
            "event_id": f"g{new_event.id}",
            "title": new_event.title,
            "subtitle": new_event.subtitle,
            "start": new_event.start,
            "end": new_event.end,
            "type": "global"
        }

        return JSONResponse(status_code=201, content={"message": "Global event created", "event": event_json})
    if calendar_event.type == "personal":
        new_personal_event = NewUserCalendarEvent(
            title=calendar_event.title,
            subtitle=calendar_event.subtitle,
            start=calendar_event.start,
            end=calendar_event.end,
            user_id=user.id
        )
        db.add(new_personal_event)
        db.commit()
        db.refresh(new_personal_event)

        event_json = {
            "event_id": f"p{new_personal_event.id}",
            "title": new_personal_event.title,
            "subtitle": new_personal_event.subtitle,
            "start": new_personal_event.start,
            "end": new_personal_event.end,
            "type": "personal"
        }

        return JSONResponse(status_code=201, content={"message": "Personal event created", "event": event_json})
    if calendar_event.type == "team":
        # Check if the user is in a team
        if not user.team_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to create team events")
        # Create the team event
        new_team_event = NewTeamCalendarEvent(
            title=calendar_event.title,
            subtitle=calendar_event.subtitle,
            start=calendar_event.start,
            end=calendar_event.end,
            team_id=user.team_id
        )
        db.add(new_team_event)
        db.commit()
        db.refresh(new_team_event)

        event_json = {
            "event_id": f"t{new_team_event.id}",
            "title": new_team_event.title,
            "subtitle": new_team_event.subtitle,
            "start": new_team_event.start,
            "end": new_team_event.end,
            "type": "team"
        }

        return JSONResponse(status_code=201, content={"message": "Team event created", "event": event_json})

        # Check if the user is a student or TA
        # if role not in [RoleType.STUDENT, RoleType.TA]:
            # raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to create personal events")
        # Create the personal event
        # new_event = NewGlobalCalendarEvent(
        #     title=calendar_event.title,
        #     subtitle=calendar_event.subtitle,
        #     start=calendar_event.start,
        #     end=calendar_event.end
        # )

        # db.add(new_event)
        # db.commit()
        # db.refresh(new_event)

        # return JSONResponse(status_code=201, content={"message": "Personal event created", "event": new_event})
        
        

    
    


    
    

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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    # user_id: int = Depends(resolve_token)
):
    user = current_user["user"]
    role = current_user["role"]

    events = []
    # Get the global events
    global_events_db = db.query(NewGlobalCalendarEvent).all()
    global_events = []
    for event in global_events_db:
        global_events.append({
            "event_id": f"g{event.id}",
            "title": event.title,
            "subtitle": event.subtitle,
            "start": event.start,
            "end": event.end,
            "type": "global"
        })
        events += global_events
    
    user_events_db = db.query(NewUserCalendarEvent).filter_by(user_id=user.id).all()
    user_events = []
    for event in user_events_db:
        user_events.append({
            "event_id": f"p{event.id}",
            "title": event.title,
            "subtitle": event.subtitle,
            "start": event.start,
            "end": event.end,
            "type": "personal"
        })
        events += user_events
    if user.team_id:
        team_events_db = db.query(NewTeamCalendarEvent).filter_by(team_id=user.team_id).all()
        team_events = []
        for event in team_events_db:
            team_events.append({
                "event_id": f"t{event.id}",
                "title": event.title,
                "subtitle": event.subtitle,
                "start": event.start,
                "end": event.end,
                "type": "team"
            })
        events += team_events
    
    
    
    return JSONResponse(status_code=201, content=events)
    # return {"message": "Calendar retrieved", "events": global_events}

@router.delete("/delete/{event_id}")
def delete_calendar_event(
    event_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    # user_id: int = Depends(resolve_token)
):
    user = current_user["user"]
    role = current_user["role"]
    if event_id[0] == "g":
        # Check if the user is professor
        if role != RoleType.PROF:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete global events")
        event_id = int(event_id[1:])
        # Check if the event exists
        event = db.query(NewGlobalCalendarEvent).filter_by(id=event_id).first()
        if not event:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
        
        # Delete the event
        db.delete(event)
        db.commit()
        return JSONResponse(status_code=200, content={"message": "Event deleted"})

    elif event_id[0] == "p":
        # Check if event exists
        event = db.query(NewUserCalendarEvent).filter_by(id=event_id).first()
        if not event:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
        
        # Check if the user is the creator of the event
        if event.user_id != user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete this event")
        
        # Delete the event
        db.delete(event)
        db.commit()
        return JSONResponse(status_code=200, content={"message": "Event deleted"})

    elif event_id[0] == "t":
        # Check if the user is in a team
        if not user.team_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete team events")
        # Check if event exists
        event = db.query(NewTeamCalendarEvent).filter_by(id=event_id).first()
        if not event:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
        
        # Check if the user is the creator of the event
        if event.team_id != user.team_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete this event")




        event = db.query(NewTeamCalendarEvent).filter_by(id=event_id).first()
        if not event:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
        

        db.delete(event)
        db.commit()
        return JSONResponse(status_code=200, content={"message": "Event deleted"})
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid event ID")



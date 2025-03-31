from sqlalchemy.orm import Session
from ..models.user import User
from ..models.global_calendar_event import GlobalCalendarEvent
from ..models.user_calendar_event import UserCalendarEvent
from ..models.team_calendar_event import TeamCalendarEvent

def get_global_events(db: Session):
    events = db.query(GlobalCalendarEvent).first()
    return events.events if events else []

def get_personal_events(user: User, db: Session):
    events = db.query(UserCalendarEvent).filter(UserCalendarEvent.creator_id == user.id).first()
    return events.events if events else []

def get_team_events(user: User, db: Session):
    if user.team_id:
        events = db.query(TeamCalendarEvent).filter(TeamCalendarEvent.creator_id == user.team_id).first()
        return events.events if events else []
    return []

def get_events(user: User, db: Session):
    global_events = get_global_events(db)
    personal_events = get_personal_events(user, db)
    team_events = get_team_events(user, db)
    return {
        "global": global_events,
        "personal": personal_events,
        "team": team_events
    } 

def overwrite_global_events(events, db: Session):
    '''
    Overwrite the global events with the new events
    '''
    top_row = db.query(GlobalCalendarEvent).first()
    if top_row:
        print(events)
        top_row.events = events
    else:
        top_row = GlobalCalendarEvent(events=events)
        db.add(top_row)
    db.commit()
    db.refresh(top_row)


def overwrite_personal_events(user: User, events, db: Session):
    '''
    Overwrite the personal events with the new events
    '''
    row = db.query(UserCalendarEvent).filter_by(creator_id=user.id).first()
    if row:
        row.events = events
    else:
        row = UserCalendarEvent(events=events, creator_id=user.id)
        db.add(row)
    db.commit()
    db.refresh(row)

def overwrite_team_events(user: User, events, db: Session):
    '''
    Overwrite the team events with the new events
    '''
    teams = user.teams
    for team in teams:
        row = db.query(TeamCalendarEvent).filter_by(creator_id=team.id).first()
        if row:
            row.events = events
        else:
            row = TeamCalendarEvent(events=events, creator_id=team.id)
            db.add(row)
    db.commit()
    db.refresh(row)

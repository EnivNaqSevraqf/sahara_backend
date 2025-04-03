from sqlalchemy.orm import Session
from ..models.announcement import Announcement
from ..models.announcement_response import AnnouncementResponse
from ..models.team_announcement_response import TeamAnnouncementResponse

def get_announcement(db: Session, announcement_id: int):
    return db.query(Announcement).filter(Announcement.id == announcement_id).first()

def get_announcement_response(db: Session, announcement_response_id: int):
    return db.query(AnnouncementResponse).filter(AnnouncementResponse.id == announcement_response_id).first()

def get_team_announcement_response(db: Session, team_announcement_response_id: int):
    return db.query(TeamAnnouncementResponse).filter(TeamAnnouncementResponse.id == team_announcement_response_id).first()

def create_announcement(db: Session, announcement_data: dict):
    announcement = Announcement(**announcement_data)
    db.add(announcement)
    db.commit()
    db.refresh(announcement)
    return announcement

def create_announcement_response(db: Session, announcement_response_data: dict):
    announcement_response = AnnouncementResponse(**announcement_response_data)
    db.add(announcement_response)
    db.commit()
    db.refresh(announcement_response)
    return announcement_response

def create_team_announcement_response(db: Session, team_announcement_response_data: dict):
    team_announcement_response = TeamAnnouncementResponse(**team_announcement_response_data)
    db.add(team_announcement_response)
    db.commit()
    db.refresh(team_announcement_response)
    return team_announcement_response

def update_announcement(db: Session, announcement_id: int, announcement_data: dict):
    announcement = get_announcement(db, announcement_id)
    if announcement:
        for key, value in announcement_data.items():
            setattr(announcement, key, value)
        db.commit()
        db.refresh(announcement)
    return announcement

def update_announcement_response(db: Session, announcement_response_id: int, announcement_response_data: dict):
    announcement_response = get_announcement_response(db, announcement_response_id)
    if announcement_response:
        for key, value in announcement_response_data.items():
            setattr(announcement_response, key, value)
        db.commit()
        db.refresh(announcement_response)
    return announcement_response

def update_team_announcement_response(db: Session, team_announcement_response_id: int, team_announcement_response_data: dict):
    team_announcement_response = get_team_announcement_response(db, team_announcement_response_id)
    if team_announcement_response:
        for key, value in team_announcement_response_data.items():
            setattr(team_announcement_response, key, value)
        db.commit()
        db.refresh(team_announcement_response)
    return team_announcement_response

def delete_announcement(db: Session, announcement_id: int):
    announcement = get_announcement(db, announcement_id)
    if announcement:
        db.delete(announcement)
        db.commit()
        return True
    return False

def delete_announcement_response(db: Session, announcement_response_id: int):
    announcement_response = get_announcement_response(db, announcement_response_id)
    if announcement_response:
        db.delete(announcement_response)
        db.commit()
        return True
    return False

def delete_team_announcement_response(db: Session, team_announcement_response_id: int):
    team_announcement_response = get_team_announcement_response(db, team_announcement_response_id)
    if team_announcement_response:
        db.delete(team_announcement_response)
        db.commit()
        return True
    return False 
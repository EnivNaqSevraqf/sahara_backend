from sqlalchemy.orm import Session
from ..models.team import Team
from ..models.user import User
from ..models.team_member import TeamMember
from ..models.team_invitation import TeamInvitation
from fastapi import HTTPException
from fastapi.responses import JSONResponse

def get_team(db: Session, team_id: int):
    return db.query(Team).filter(Team.id == team_id).first()

def get_team_member(db: Session, team_member_id: int):
    return db.query(TeamMember).filter(TeamMember.id == team_member_id).first()

def get_team_invitation(db: Session, team_invitation_id: int):
    return db.query(TeamInvitation).filter(TeamInvitation.id == team_invitation_id).first()

def create_team(db: Session, team_data: dict):
    team = Team(**team_data)
    db.add(team)
    db.commit()
    db.refresh(team)
    return team

def create_team_member(db: Session, team_member_data: dict):
    team_member = TeamMember(**team_member_data)
    db.add(team_member)
    db.commit()
    db.refresh(team_member)
    return team_member

def create_team_invitation(db: Session, team_invitation_data: dict):
    team_invitation = TeamInvitation(**team_invitation_data)
    db.add(team_invitation)
    db.commit()
    db.refresh(team_invitation)
    return team_invitation

def update_team(db: Session, team_id: int, team_data: dict):
    team = get_team(db, team_id)
    if team:
        for key, value in team_data.items():
            setattr(team, key, value)
        db.commit()
        db.refresh(team)
    return team

def update_team_member(db: Session, team_member_id: int, team_member_data: dict):
    team_member = get_team_member(db, team_member_id)
    if team_member:
        for key, value in team_member_data.items():
            setattr(team_member, key, value)
        db.commit()
        db.refresh(team_member)
    return team_member

def update_team_invitation(db: Session, team_invitation_id: int, team_invitation_data: dict):
    team_invitation = get_team_invitation(db, team_invitation_id)
    if team_invitation:
        for key, value in team_invitation_data.items():
            setattr(team_invitation, key, value)
        db.commit()
        db.refresh(team_invitation)
    return team_invitation

def delete_team(db: Session, team_id: int):
    team = get_team(db, team_id)
    if team:
        db.delete(team)
        db.commit()
        return True
    return False

def delete_team_member(db: Session, team_member_id: int):
    team_member = get_team_member(db, team_member_id)
    if team_member:
        db.delete(team_member)
        db.commit()
        return True
    return False

def delete_team_invitation(db: Session, team_invitation_id: int):
    team_invitation = get_team_invitation(db, team_invitation_id)
    if team_invitation:
        db.delete(team_invitation)
        db.commit()
        return True
    return False

def get_team(db: Session):
    teams = db.query(Team).all()
    return teams

def get_student_team(current_user: User, db: Session):
    team = db.query(Team).filter(Team.members.any(id=current_user.id)).first()
    return team

def get_allocation(n: int, db: Session):
    # Get all teams and TAs
    teams = db.query(Team).all()
    tas = db.query(User).filter(User.role_id == 3).all()  # Assuming 3 is TA role_id
    
    # Implementation of allocation logic
    # This is a placeholder - actual implementation would be more complex
    return {
        "teams": teams,
        "tas": tas,
        "n": n
    }

def setFormedTeams(db: Session):
    try:
        # Get all teams
        teams = db.query(Team).all()
        
        # Get all students
        students = db.query(User).filter(User.role_id == 2).all()  # Assuming 2 is student role_id
        
        # Create teams for students who don't have one
        for student in students:
            if not student.team_id:
                # Create a new team
                team = Team(name=f"Team {student.id}")
                db.add(team)
                db.commit()
                db.refresh(team)
                
                # Assign student to team
                student.team_id = team.id
                db.commit()
        
        return JSONResponse(status_code=200, content={
            "message": "Teams formed successfully",
            "team_count": len(teams)
        })
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error forming teams: {str(e)}")

def setbetaTestPairs(db: Session):
    try:
        # Get all teams
        teams = db.query(Team).all()
        
        # Get all students
        students = db.query(User).filter(User.role_id == 2).all()  # Assuming 2 is student role_id
        
        # Create pairs for students who don't have one
        for student in students:
            if not student.team_id:
                # Find another student without a team
                partner = next((s for s in students if s.id != student.id and not s.team_id), None)
                
                if partner:
                    # Create a new team
                    team = Team(name=f"Beta Test Pair {student.id}-{partner.id}")
                    db.add(team)
                    db.commit()
                    db.refresh(team)
                    
                    # Assign both students to team
                    student.team_id = team.id
                    partner.team_id = team.id
                    db.commit()
        
        return JSONResponse(status_code=200, content={
            "message": "Beta test pairs formed successfully",
            "team_count": len(teams)
        })
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error forming beta test pairs: {str(e)}") 
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from app.db.session import get_db
from app.core.security.auth import get_current_user
from app.models.user import User, RoleType
from app.models.team import Team, Team_TA
from app.schemas.team import TeamBase, TeamDisplay
from app.utils.helpers import paginate_results

router = APIRouter(prefix="/teams", tags=["teams"])

@router.post("/", response_model=TeamDisplay)
async def create_team(
    team: TeamBase,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user["role"] != RoleType.PROF:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only professors can create teams"
        )

    # Check if team name is unique
    existing_team = db.query(Team).filter(Team.name == team.team_name).first()
    if existing_team:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Team name {team.team_name} already exists"
        )

    new_team = Team(name=team.team_name)
    db.add(new_team)
    db.commit()
    db.refresh(new_team)

    return TeamDisplay(
        id=new_team.id,
        team_name=new_team.name,
        skills=[]
    )

@router.get("/{team_id}")
async def get_team(
    team_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found"
        )

    # Check access rights
    user = current_user["user"]
    if user.role.role == RoleType.STUDENT and user.team_id != team_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only view your own team"
        )

    return {
        "id": team.id,
        "name": team.name,
        "members": [
            {
                "id": member.id,
                "name": member.name,
                "email": member.email,
                "role": member.role.role.value
            }
            for member in team.members
        ],
        "skills": [skill.name for skill in team.skills]
    }

@router.post("/{team_id}/members")
async def add_team_member(
    team_id: int,
    user_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user["role"] != RoleType.PROF:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only professors can modify team members"
        )

    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found"
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    if user in team.members:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is already a member of this team"
        )

    team.members.append(user)
    db.commit()

    return {"message": f"User {user.name} added to team {team.name}"}

@router.post("/{team_id}/ta")
async def assign_ta(
    team_id: int,
    ta_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user["role"] != RoleType.PROF:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only professors can assign TAs"
        )

    # Verify team exists
    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found"
        )

    # Verify TA exists and has TA role
    ta = db.query(User).filter(
        User.id == ta_id,
        User.role.has(role=RoleType.TA)
    ).first()
    if not ta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="TA not found or user is not a TA"
        )

    # Check if TA is already assigned to this team
    existing_assignment = db.query(Team_TA).filter(
        Team_TA.team_id == team_id,
        Team_TA.ta_id == ta_id
    ).first()
    if existing_assignment:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="TA is already assigned to this team"
        )

    # Create new TA assignment
    ta_assignment = Team_TA(team_id=team_id, ta_id=ta_id)
    db.add(ta_assignment)
    db.commit()

    return {"message": f"TA {ta.name} assigned to team {team.name}"}
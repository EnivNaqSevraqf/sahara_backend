from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from ..database.db import get_db
from ..models.user import User
from ..models.roles import Role, RoleType
from ..models.skills import Skill
from ..models.team import Team
from ..dependencies.auth import prof_or_ta_required, prof_required, oauth2_scheme
from ..schemas.auth_schemas import UserBase
from ..schemas.skill_schemas import AssignSkillsRequest
from ..config.config import SECRET_KEY, ALGORITHM
from fastapi.responses import JSONResponse
import jwt

router = APIRouter(
    prefix="/api/users",
    tags=["API Users"]
)

router2=APIRouter()

@router.get("/{user_id}/skills")
async def get_user_skills(user_id: int, db: Session = Depends(get_db)):
    """Get all skills for a specific user (TA)"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Check if user is a TA
    role = db.query(Role).filter(Role.id == user.role_id).first()
    if role.role != RoleType.TA:
        raise HTTPException(status_code=400, detail="Skills can only be assigned to TAs")
    
    skills = user.skills
    results = []
    for skill in skills:
        results.append({
            "id": skill.id,
            "name": skill.name,
            "bgColor": skill.bgColor,
            "color": skill.color,
            "icon": skill.icon
        })
    
    return JSONResponse(status_code=200, content=results)

@router.post("/assign-skills")
async def assign_skills_to_user(request: AssignSkillsRequest, db: Session = Depends(get_db), token: str = Depends(prof_or_ta_required)):
    """Assign skills to a user (TA)"""
    try:
        user = db.query(User).filter(User.id == request.user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Check if user is a TA
        role = db.query(Role).filter(Role.id == user.role_id).first()
        if role.role != RoleType.TA:
            raise HTTPException(status_code=400, detail="Skills can only be assigned to TAs")
        
        # Get all skills by IDs
        skills = db.query(Skill).filter(Skill.id.in_(request.skill_ids)).all()
        if len(skills) != len(request.skill_ids):
            raise HTTPException(status_code=400, detail="Some skill IDs are invalid")
        
        # Clear existing skills and assign new ones
        user.skills = skills
        db.commit()
        
        return JSONResponse(status_code=200, content={
            "message": "Skills assigned successfully",
            "user_id": user.id,
            "skill_count": len(skills)
        })
    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error assigning skills: {str(e)}")



@router2.get("/user/me")
async def get_user_data(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """
    Fetch user data using the token.
    """
    try:
        # Decode the token to get the username
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if not username:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )
        
        # Fetch the user from the database
        user = db.query(User).filter(User.username == username).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Fetch the user's role
        role = db.query(Role).filter(Role.id == user.role_id).first()
        
        # Fetch the user's team name
        team_name = None
        if user.team_id:
            team = db.query(Team).filter(Team.id == user.team_id).first()
            team_name = team.name if team else None
        
        # Return user data
        return {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "username": user.username,
            "role": role.role.value,
            "team_name": team_name  # Send team name instead of team ID
        }
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired"
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching user data: {str(e)}"
        )
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from ..database.db import get_db
from ..models.team import Team
from ..models.user import User
from ..models.skills import Skill, TeamSkill, UserSkill, team_skills
from ..utils.team_matching import get_allocation
from ..models.team_ta import Team_TA
from ..dependencies.auth import prof_required
router = APIRouter(
    prefix="/match",
    tags=["Match"]
)

@router.get("/{n}", response_model=dict)
async def create_match(n: int, db: Session = Depends(get_db), token: str = Depends(prof_required)):
    if n <= 0:
        raise HTTPException(status_code=400, detail="Number of TAs per team must be positive")
    
    try:
        # Get allocations using matching algorithm
        allocations = get_allocation(n, db)
        
        # Clear existing team_tas entries
        db.query(Team_TA).delete()
        
        # Insert new allocations
        for allocation in allocations:
            team_id = allocation["team_id"]
            for ta_id in allocation["assigned_ta_ids"]:
                new_team_ta = Team_TA(
                    team_id=team_id,
                    ta_id=ta_id
                )
                db.add(new_team_ta)
        
        db.commit()
        return {"message": "allocation is done"}
    
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/", response_model=dict)
async def get_match(db: Session = Depends(get_db)):
    try:
        # Get all teams with their skills and TAs
        teams = db.query(Team).all()
        results = []
        
        for team in teams:
            # Get team skills
            skills = db.query(Skill).join(team_skills).filter(team_skills.c.team_id == team.id).all()
            
            # Get assigned TAs
            tas = (
                db.query(User)
                .join(Team_TA, User.id == Team_TA.ta_id)
                .filter(Team_TA.team_id == team.id)
                .all()
            )
            
            results.append({
                "team_id": team.id,
                "team_name": team.name,
                "skills": [
                    {
                        "id": skill.id,
                        "name": skill.name,
                        "bgColor": skill.bgColor,
                        "color": skill.color,
                        "icon": skill.icon
                    }
                    for skill in skills
                ],
                "tas": [
                    {
                        "id": ta.id,
                        "name": ta.name
                    }
                    for ta in tas
                ]
            })
        
        return {"teams": results}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
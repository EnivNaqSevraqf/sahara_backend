from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from database.db import get_db
from models.skills import Skill
from models.user import User
from dependencies.auth import prof_or_ta_required, prof_required
from pydantic import BaseModel
from schemas.skill_schemas import SkillCreate, AssignSkillsRequest, SkillRequest
from fastapi.responses import JSONResponse

router = APIRouter(
    prefix="/api/skills",
    tags=["API Skills"]
)

router2=APIRouter()

@router.get("/")
async def get_all_skills(db: Session = Depends(get_db)):
    """Get all skills from the database"""
    skills = db.query(Skill).all()
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

@router.post("/create")
async def create_skill(skill: SkillCreate, db: Session = Depends(get_db), token: str = Depends(prof_or_ta_required)):
    """Create a new skill"""
    try:
        # Check if skill with same name already exists
        existing = db.query(Skill).filter(Skill.name == skill.name).first()
        if existing:
            raise HTTPException(status_code=400, detail=f"Skill with name '{skill.name}' already exists")
        
        # Create new skill
        new_skill = Skill(
            name=skill.name,
            bgColor=skill.bgColor,
            color=skill.color,
            icon=skill.icon
        )
        
        db.add(new_skill)
        db.commit()
        db.refresh(new_skill)
        
        return JSONResponse(status_code=201, content={
            "id": new_skill.id,
            "name": new_skill.name,
            "bgColor": new_skill.bgColor,
            "color": new_skill.color,
            "icon": new_skill.icon
        })
    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error creating skill: {str(e)}")

@router.delete("/{skill_id}")
async def delete_skill(skill_id: int, db: Session = Depends(get_db), token: str = Depends(prof_required)):
    """Delete a skill (professors only)"""
    try:
        skill = db.query(Skill).filter(Skill.id == skill_id).first()
        if not skill:
            raise HTTPException(status_code=404, detail="Skill not found")
        
        # Remove the skill from all users that have it
        for user in skill.users:
            user.skills.remove(skill)
        
        # Delete the skill
        db.delete(skill)
        db.commit()
        
        return JSONResponse(status_code=200, content={
            "message": "Skill deleted successfully",
            "id": skill_id
        })
    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error deleting skill: {str(e)}")
    


@router2.post("/create-skill")
def create_skill( skill_req: SkillRequest):
    return {"bgColor" : skill_req.bgColor}
from sqlalchemy.orm import Session
from ..models.skills import Skill
from ..models.user import User
from ..models.team import Team
from ..models.skills import UserSkills, TeamSkills
from fastapi import HTTPException
from fastapi.responses import JSONResponse

def get_all_skills(db: Session):
    skills = db.query(Skill).all()
    return skills

def get_user_skills(user: User, db: Session):
    user_skills = db.query(UserSkills).filter(UserSkills.user_id == user.id).first()
    return user_skills.skills if user_skills else []

def get_team_skills(user: User, db: Session):
    if user.team_id:
        team_skills = db.query(TeamSkills).filter(TeamSkills.team_id == user.team_id).first()
        return team_skills.skills if team_skills else []
    return []

def get_skills(user: User, db: Session):
    user_skills = get_user_skills(user, db)
    team_skills = get_team_skills(user, db)
    return {
        "user": user_skills,
        "team": team_skills
    }

def create_user_skills(user: User, skills: list, db: Session):
    user_skills = UserSkills(user_id=user.id, skills=skills)
    db.add(user_skills)
    db.commit()

def create_team_skills(user: User, skills: list, db: Session):
    if user.team_id:
        team_skills = TeamSkills(team_id=user.team_id, skills=skills)
        db.add(team_skills)
        db.commit()

def update_user_skills(user: User, skills: list, db: Session):
    user_skills = db.query(UserSkills).filter(UserSkills.user_id == user.id).first()
    if user_skills:
        user_skills.skills = skills
        db.commit()

def update_team_skills(user: User, skills: list, db: Session):
    if user.team_id:
        team_skills = db.query(TeamSkills).filter(TeamSkills.team_id == user.team_id).first()
        if team_skills:
            team_skills.skills = skills
            db.commit()

def delete_user_skills(user: User, db: Session):
    user_skills = db.query(UserSkills).filter(UserSkills.user_id == user.id).first()
    if user_skills:
        db.delete(user_skills)
        db.commit()

def delete_team_skills(user: User, db: Session):
    if user.team_id:
        team_skills = db.query(TeamSkills).filter(TeamSkills.team_id == user.team_id).first()
        if team_skills:
            db.delete(team_skills)
            db.commit()

def create_skill(skill_req: dict, db: Session):
    try:
        skill = Skill(
            name=skill_req.name,
            bgColor=skill_req.bgColor,
            color=skill_req.color,
            icon=skill_req.icon
        )
        db.add(skill)
        db.commit()
        db.refresh(skill)
        return skill
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error creating skill: {str(e)}")

def update_team_skills(skills: list, db: Session, current_user: User):
    try:
        team = db.query(Team).filter(Team.members.any(id=current_user.id)).first()
        if not team:
            raise HTTPException(status_code=404, detail="Team not found")
        
        # Get all skills
        skill_objects = db.query(Skill).filter(Skill.id.in_(skills)).all()
        if len(skill_objects) != len(skills):
            raise HTTPException(status_code=400, detail="Some skill IDs are invalid")
        
        # Update team skills
        team.skills = skill_objects
        db.commit()
        
        return JSONResponse(status_code=200, content={
            "message": "Team skills updated successfully",
            "team_id": team.id,
            "skill_count": len(skills)
        })
    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error updating team skills: {str(e)}") 
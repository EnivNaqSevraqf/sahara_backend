from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
import pandas as pd
from sqlalchemy.orm import Session
from typing import List
from ..database.db import get_db
from ..models.team import Team
from ..models.user import User
from ..dependencies.auth import prof_or_ta_required, prof_required
from pydantic import BaseModel
from fastapi.responses import JSONResponse
from ..schemas.skill_schemas import AssignTeamSkillsRequest
from ..models.skills import Skill
from ..dependencies.auth import get_current_user
from ..models.roles import RoleType
from ..schemas.team_schemas import TeamNameUpdateRequest, UpdateTAsRequest
import os
from ..models.team_ta import Team_TA




router = APIRouter()



@router.get("/team")
def get_team(db: Session = Depends(get_db)):
    users = db.query(Team).all()
    return_data = []
    #role_id_to_role = { 1 : "Professor", 2 : "Student", 3 : "TA"}
    for user in users:
        user_data = {}
        user_data["id"] = user.id
        user_data["name"] = user.name
        user_data["details"] = user.members
        return_data.append(user_data)
    return return_data

@router.get("/teams")
async def get_student_team(
    current_user: dict[User, str] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get student's team and member data with feedback submission validation"""
    try:
        user = current_user["user"]
        
        # Check if user is a student
        if current_user["role"] != RoleType.STUDENT:
            raise HTTPException(
                status_code=403,
                detail="Only students can access this endpoint"
            )

        # Check if user has been assigned to a team
        if not user.teams:
            raise HTTPException(
                status_code=404,
                detail="You have not been assigned to a team"
            )
            
        team = user.teams[0]  # Get the student's team

        # Get all team members including the current user
        team_members = [
            {
                "id": member.id,
                "name": member.name,
                "email": member.email,
                "is_current_user": member.id == user.id
            }
            for member in team.members
        ]

        skills = team.skills
        skill_data = []
        for skill in skills:
            skill_data.append({
                "id": skill.id,
                "name": skill.name,
                "bgColor": skill.bgColor,
                "color": skill.color,
                "icon": skill.icon
            })
        all_skills = db.query(Skill).all()
        all_skills_data = []
        for skill in all_skills:
            all_skills_data.append({
                "id": skill.id,
                "name": skill.name,
                "bgColor": skill.bgColor,
                "color": skill.color,
                "icon": skill.icon
            })
        return {
            "team_id": team.id,
            "team_name": team.name,
            "members": team_members,
            "skills": skill_data,
            "all_skills":  all_skills
        }
        
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@router.put("/teams/skills")
def update_team_skills(
    skills: List[int],
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Update team skills
    """
    try:
    # if 1:
        user = current_user["user"]
        if current_user["role"] != RoleType.STUDENT:
            raise HTTPException(status_code=403, detail="Only students can access this endpoint")
        
        if not user.teams:
            raise HTTPException(status_code=404, detail="User has no team assigned")
        team = user.teams[0]  # Get the student's team
        if not team:
            raise HTTPException(status_code=404, detail="Team not found")
        
        # Clear existing skills and assign new ones
        team.skills = []
        for skill_id in skills:
            skill = db.query(Skill).filter(Skill.id == skill_id).first()
            if skill:
                team.skills.append(skill)
        db.commit()
        
        return JSONResponse(status_code=200, content={"message": "Team skills updated successfully"})
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/teams/FormedTeams")
def setFormedTeams(db: Session = Depends(get_db)):
    teams = db.query(Team).all()

    return_data = []
    for team in teams:
        team_data = {
            "number": team.id,
            "name": team.name,
            "details": "",  # Add details if needed
            "members": [member.name for member in team.members]  # Extract member names
        }
        return_data.append(team_data)

    return return_data

@router.get("/teams/betaTestPairs")
def setbetaTestPairs(db: Session = Depends(get_db)):
    teams = db.query(Team).all()

    return_data = []
    for team in teams:
        team_data = {
            "number": team.id,
            "name": team.name,
            "details": "",  # Add details if needed
            "members": [member.name for member in team.members]  # Extract member names
        }
        return_data.append(team_data)

    return return_data

@router.put("/teams/name")
async def update_team_name(
    request: TeamNameUpdateRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Extract user and role
    user = current_user["user"]
    role = current_user["role"]
    
    # Verify that the user is a student
    if role != RoleType.STUDENT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only students can update team names"
        )
    
    # Get the user's team
    teams = user.teams
    if not teams:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="You are not a member of any team"
        )
    
    # Update the team name
    team = teams[0]  # Assuming a student is only in one team
    team.name = request.name
    
    try:
        db.commit()
        return {
            "message": "Team name updated successfully",
            "team_id": team.id,
            "team_name": team.name
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update team name: {str(e)}"
        )





@router.get("api/teams/{team_id}/skills")
async def get_team_skills(team_id: int, db: Session = Depends(get_db)):
    """Get all skills for a specific team"""
    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    
    skills = team.skills
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

@router.post("/api/teams/assign-skills")
async def assign_skills_to_team(request: AssignTeamSkillsRequest, db: Session = Depends(get_db), token: str = Depends(prof_or_ta_required)):
    """Assign skills to a team"""
    try:
        team = db.query(Team).filter(Team.id == request.team_id).first()
        if not team:
            raise HTTPException(status_code=404, detail="Team not found")
        
        # Get all skills by IDs
        skills = db.query(Skill).filter(Skill.id.in_(request.skill_ids)).all()
        if len(skills) != len(request.skill_ids):
            raise HTTPException(status_code=400, detail="Some skill IDs are invalid")
        
        # Clear existing skills and assign new ones
        team.skills = skills
        db.commit()
        
        return JSONResponse(status_code=200, content={
            "message": "Skills assigned successfully to team",
            "team_id": team.id,
            "skill_count": len(skills)
        })
    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error assigning skills to team: {str(e)}")


@router.post("/teams/upload-csv/")
async def upload_csv(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="Invalid file format. Please upload a CSV file.")

    try:
        # Save the uploaded file to a temporary location
        temp_file_path = f"temp_{file.filename}"
        with open(temp_file_path, "wb") as temp_file:
            temp_file.write(file.file.read())

        # Read the CSV file using pandas
        df = pd.read_csv(temp_file_path)

        # Validate the CSV format
        required_columns = ['team_name', 'member1', 'member2', 'member3', 'member4', 'member5', 'member6', 'member7', 'member8', 'member9', 'member10']
        print(df.columns)
        for _column_name in required_columns:
            if _column_name not in df.columns:
                raise HTTPException(status_code=400, detail=f"Invalid CSV format. Missing column: {_column_name}")

        # Check if all members exist in the Users database and perform other checks
        team_names = set()
        members_set = list()
        for _, row in df.iterrows():
            team_name = row['team_name']
            members = []
            for i in range(1, 11):
                members.append(row[f'member{i}'])

            # members = [row[f'member{i}'] for i in range(1, 11) if pd.notna(row[f'member{i}'])]

            if team_name in team_names:
                raise HTTPException(status_code=400, detail=f"Invalid file: Duplicate team name '{team_name}' found.")
            
            team_names.add(team_name)

            for member_name in members:
                user = db.query(User).filter_by(username=member_name).first()
                if not user:
                    raise HTTPException(status_code=400, detail=f"Invalid file: User '{member_name}' does not exist in the database.")
                if user.team_id:
                    raise HTTPException(status_code=400, detail=f"Invalid file: User '{member_name}' is already assigned to a team.")
                if member_name in members_set:
                    raise HTTPException(status_code=400, detail=f"Invalid file: User '{member_name}' is assigned to multiple teams.")
            members_set.append(members)

        # Get the highest team ID present in the database
        # max_team_id = db.query(func.max(Team.id)).scalar() or 0


        team_names = list(team_names)
        print("Team names: ", team_names)
        print("Members set:", members_set)
        for i in range(len(team_names)):
            team_name = team_names[i]
            members = members_set[i]
            team = Team(name = team_name)
            db.add(team)
            for member in members:
                user = db.query(User).filter_by(username=member).first()
                print("Over here")
                if user:
                    team.members.append(user)
                    user.team_id = team.id
        db.commit()

        
        # Process each row in the CSV file
        # for _, row in 
        #     team_name = row['team_name']
        #     members = []
        #     for i in range(10):
        #         print(row[f'member{i}'])
        #         members.append(row[f'member{i}'])
        #     print(members)
        #     # Create a new team
        #     team = Team(name=team_name)
        #     db.add(team)

        #     # Add members to the team
        #     for member_name in members:
        #         user = db.query(User).filter_by(name=member_name).first()
        #         if user:
        #             # check if user is in team already
        #             # if user not in team.members:
        #             #     # check if user is already in a team
        #             #     if user.team_id is None:
        #             #         # Add the user to the team
        #             team.members.append(user)
        #             user.team_id = team.id  # Assign the team ID to the user
        #             print("Added user to team:", user.name, "in team:", team.name)
        # print("Committed the changes")
        # db.commit()

        # Clean up the temporary file
        os.remove(temp_file_path)

        return {"detail": "File uploaded and data saved successfully!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    

@router.post("/teams/{team_id}/update-tas")
async def update_team_tas(
    team_id: int,
    request: UpdateTAsRequest,
    db: Session = Depends(get_db),
    token: str = Depends(prof_or_ta_required)
):
    """Update TA assignments for a specific team"""
    try:
        # Verify team exists
        team = db.query(Team).filter(Team.id == team_id).first()
        if not team:
            raise HTTPException(status_code=404, detail="Team not found")

        # Verify all TAs exist and are actually TAs
        tas = db.query(User).filter(
            User.id.in_(request.ta_ids),
            User.role_id == 3  # role_id 3 is for TAs
        ).all()

        if len(tas) != len(request.ta_ids):
            raise HTTPException(
                status_code=400,
                detail="One or more selected users are not TAs or do not exist"
            )

        # Delete existing TA assignments for this team
        db.query(Team_TA).filter(Team_TA.team_id == team_id).delete()

        # Create new TA assignments
        for ta_id in request.ta_ids:
            new_assignment = Team_TA(
                team_id=team_id,
                ta_id=ta_id
            )
            db.add(new_assignment)

        db.commit()
        return {"message": "TA assignments updated successfully"}

    except HTTPException as he:
        db.rollback()
        raise he
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error updating TA assignments: {str(e)}"
        )
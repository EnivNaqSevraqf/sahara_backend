
from fastapi import HTTPException
from sqlalchemy.orm import Session
from ..models.team import Team
from ..models.user import User
from ..models.skills import UserSkill, TeamSkill



def get_allocation(n: int, db: Session):
    # Get all teams and TAs
    teams = db.query(Team).all()
    tas = db.query(User).filter(User.role_id == 3).all()
    
    if not tas:
        raise HTTPException(status_code=400, detail="No TAs available")
    
    # Calculate maximum teams per TA
    max_teams_per_ta = (len(teams) * n) // len(tas)
    if (len(teams)*n)>len(tas)*max_teams_per_ta:
        max_teams_per_ta = 1 + max_teams_per_ta
    if max_teams_per_ta == 0:
        max_teams_per_ta = 1
    
    # Dictionary to track number of teams assigned to each TA
    ta_assignments = {ta.id: 0 for ta in tas}
    allocations = []
    all_matches = []

    # Calculate skill matches for all team-TA pairs
    for team in teams:
        # Get team's required skills
        team_skills = set([skill[0] for skill in db.query(TeamSkill.skill_id)
            .filter(TeamSkill.team_id == team.id).all()])
        
        for ta in tas:
            # Get TA's skills
            ta_skills = set([skill[0] for skill in db.query(UserSkill.skill_id)
                .filter(UserSkill.user_id == ta.id).all()])
            
            # Calculate skill match score
            match_score = len(team_skills.intersection(ta_skills))
            
            if match_score > 0:  # Only consider pairs with at least one skill match
                all_matches.append({
                    "team_id": team.id,
                    "ta_id": ta.id,
                    "match_score": match_score
                })

    # Sort matches by match score in descending order
    all_matches.sort(key=lambda x: x["match_score"], reverse=True)

    # Create initial allocations based on best matches
    team_allocations = {team.id: [] for team in teams}

    # First pass: Assign TAs based on best skill matches
    for match in all_matches:
        team_id = match["team_id"]
        ta_id = match["ta_id"]

        # Check if team needs more TAs and TA hasn't reached their limit
        if (len(team_allocations[team_id]) < n and 
            ta_assignments[ta_id] < max_teams_per_ta):
            team_allocations[team_id].append(ta_id)
            ta_assignments[ta_id] += 1

    # Second pass: Fill remaining slots if needed
    for team_id, assigned_tas in team_allocations.items():
        while len(assigned_tas) < n:
            # Find TA with fewest assignments who isn't already assigned to this team
            available_ta = min(
                (ta_id for ta_id in ta_assignments if ta_id not in assigned_tas),
                key=lambda x: ta_assignments[x],
                default=None
            )
            
            if available_ta and ta_assignments[available_ta] < max_teams_per_ta:
                assigned_tas.append(available_ta)
                ta_assignments[available_ta] += 1
            else:
                break  # No more available TAs

    # Format the allocations
    for team_id, assigned_tas in team_allocations.items():
        allocations.append({
            "team_id": team_id,
            "assigned_ta_ids": assigned_tas
        })

    return allocations
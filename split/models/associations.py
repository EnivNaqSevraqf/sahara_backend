from sqlalchemy import Column, Integer, ForeignKey, Table
from ..database.db import Base

# Association table for User-Skills many-to-many relationship
user_skills = Table(
    "user_skills", Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id"), primary_key=True),
    Column("skill_id", Integer, ForeignKey("skills.id"), primary_key=True)
)

# Association table for Team-Skills many-to-many relationship
team_skills = Table(
    "team_skills", Base.metadata,
    Column("team_id", Integer, ForeignKey("teams.id"), primary_key=True),
    Column("skill_id", Integer, ForeignKey("skills.id"), primary_key=True)
)

# Association table for Team-User many-to-many relationship
team_members = Table(
    "team_members", Base.metadata,
    Column("team_id", Integer, ForeignKey("teams.id"), primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id"), primary_key=True)
) 
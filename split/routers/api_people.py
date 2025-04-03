from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from ..database.db import get_db
from ..models.user import User  

router = APIRouter(
    prefix="/people",
    tags=["People"]
) 

@router.get("/")
def get_people(db: Session = Depends(get_db)):
    users = db.query(User).all()
    return_data = []
    role_id_to_role = { 1 : "Professor", 2 : "Student", 3 : "TA"}
    for user in users:
        user_data = {}
        user_data["id"] = user.id
        user_data["name"] = user.name
        user_data["email"] = user.email
        user_data["role"] = role_id_to_role[user.role_id]
        return_data.append(user_data)
    return return_data
    # return {"access_token": token, "token_type": "bearer", "role": role}

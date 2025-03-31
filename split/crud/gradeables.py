from sqlalchemy.orm import Session
from ..models.gradeables import Gradeable
from ..models.gradeable_scores import GradeableScores
from typing import List, Dict, Any
import csv
from io import StringIO
from fastapi import HTTPException
from ..utils.auth import extract_students
from models.user import User

def get_gradeable_table(db: Session):
    gradeables = db.query(Gradeable).all()
    return gradeables

def get_gradeable_by_id(gradeable_id: int, db: Session):
    gradeable = db.query(Gradeable).filter(Gradeable.id == gradeable_id).first()
    if not gradeable:
        return None
    return gradeable

def get_gradeable_submissions(gradeable_id: int, db: Session):
    submissions = db.query(GradeableScores).filter(GradeableScores.gradeable_id == gradeable_id).all()
    return submissions

def parse_scores_from_csv(csv_content: str, gradeable_id: int, max_points: int, db: Session) -> List[Dict[str, Any]]:
    try:
        # Create a StringIO object to read the CSV content
        csv_file = StringIO(csv_content)
        csv_reader = csv.DictReader(csv_file)
        
        # Validate required columns
        required_columns = ['username', 'score']
        if not all(col in csv_reader.fieldnames for col in required_columns):
            raise HTTPException(
                status_code=400,
                detail=f"CSV must contain columns: {', '.join(required_columns)}"
            )
        
        # Process each row
        scores = []
        for row in csv_reader:
            try:
                username = row['username'].strip()
                score = int(row['score'])
                
                # Validate score
                if score < 0 or score > max_points:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid score {score} for user {username}. Score must be between 0 and {max_points}"
                    )
                
                # Get user
                user = db.query(User).filter(User.username == username).first()
                if not user:
                    raise HTTPException(
                        status_code=404,
                        detail=f"User not found: {username}"
                    )
                
                # Create or update score
                gradeable_score = db.query(GradeableScores).filter(
                    GradeableScores.gradeable_id == gradeable_id,
                    GradeableScores.user_id == user.id
                ).first()
                
                if gradeable_score:
                    gradeable_score.score = score
                else:
                    gradeable_score = GradeableScores(
                        gradeable_id=gradeable_id,
                        user_id=user.id,
                        score=score
                    )
                    db.add(gradeable_score)
                
                scores.append({
                    "username": username,
                    "score": score,
                    "user_id": user.id
                })
                
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid score format for user {row['username']}"
                )
        
        db.commit()
        return scores
        
    except HTTPException as he:
        db.rollback()
        raise he
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error processing CSV: {str(e)}"
        ) 
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from database.db import get_db
from models.gradeables import Gradeable  # Import your Gradeable model
from dependencies.auth import prof_or_ta_required  
from fastapi.responses import JSONResponse
router = APIRouter ()
from crud.gradeables import parse_scores_from_csv
from fastapi import FastAPIForm, File, UploadFile
from models.user import User
from models.gradeable_scores import GradeableScores

@router.get("/gradeables/")
async def get_gradeable_table(
    db: Session = Depends(get_db),
    token: str = Depends(prof_or_ta_required)
):
    """
    Get the gradeable table for professors and TAs
    """
    gradeables = db.query(Gradeable).all()
    results = []
    for gradeable in gradeables:
        results.append({
            "id": gradeable.id,
            "title": gradeable.title,
            "max_points": gradeable.max_points,
            "creator_id": gradeable.creator_id,
        })
    return JSONResponse(status_code=200, content=results)

@router.get("/gradeables/{gradeable_id}")
async def get_gradeable_by_id(
    gradeable_id: int,
    db: Session = Depends(get_db),
    token: str = Depends(prof_or_ta_required)
):
    """
    Get a specific gradeable by ID
    """
    gradeable = db.query(Gradeable).filter(Gradeable.id == gradeable_id).first()
    if not gradeable:
        raise HTTPException(status_code=404, detail="Gradeable not found")
    
    return JSONResponse(status_code=200, content={
        "id": gradeable.id,
        "title": gradeable.title,
    })

@router.get("/gradeables/{gradeable_id}/scores")
async def get_gradeable_submissions(
    gradeable_id: int,
    db: Session = Depends(get_db),
    token: str = Depends(prof_or_ta_required)
):
    """
    Get all submissions for a specific gradeable
    """
    submissions = db.query(GradeableScores).filter(GradeableScores.gradeable_id == gradeable_id).all()
    results = []
    for submission in submissions:
        results.append({
            "id": submission.id,
            "gradeable_id": submission.gradeable_id,
            "user_id": submission.user_id, 
            "name": submission.user.name,
            #"submitted_at": submission.submitted_at,
            "score": submission.score
        })
    return JSONResponse(status_code=200, content=results)

# @app.post("/gradeables/create")
# async def create_gradeable(
#     gradeable: GradeableCreateRequest,
#     file: UploadFile = File(...),
# )

# @app.post("/gradeables/{gradeable_id}/upload-scores")
# async def upload_gradeable_scores(
#     gradeable_id: int,
#     file: UploadFile = File(...),
#     db: Session = Depends(get_db),
#     token: str = Depends(prof_or_ta_required)
# ):
#     """
#     Upload scores for a specific gradeable
#     """
#     # Ensure the file is a CSV
#     if not file.filename.endswith('.csv'):
#         raise HTTPException(
#             status_code=status.HTTP_400_BAD_REQUEST,
#             detail="Only CSV files are allowed"
#         )
    
#     try:
#         # Validate gradeable exists and get max points
#         gradeable = db.query(Gradeable).filter(Gradeable.id == gradeable_id).first()
#         if not gradeable:
#             raise HTTPException(
#                 status_code=status.HTTP_404_NOT_FOUND,
#                 detail="Gradeable not found"
#             )
        
#         # Read and parse file content
#         content = await file.read()
#         content_str = content.decode('utf-8')
        
#         # Parse scores with detailed validation
#         scores = parse_scores_from_csv(
#             csv_content=content_str, 
#             gradeable_id=gradeable_id, 
#             max_points=gradeable.max_points,
#             db=db
#         )
        
#         # Bulk upsert scores
#         for score_data in scores:
#             existing_submission = db.query(GradeableScores).filter(
#                 GradeableScores.gradeable_id == gradeable_id,
#                 GradeableScores.user_id == score_data["user_id"]
#             ).first()
            
#             if existing_submission:
#                 existing_submission.score = score_data["score"]
#             else:
#                 new_submission = GradeableScores(
#                     user_id=score_data["user_id"],
#                     gradeable_id=gradeable_id,
#                     score=score_data["score"]
#                 )
#                 db.add(new_submission)
        
#         db.commit()
        
#         return JSONResponse(status_code=200, content={
#             "message": "Scores uploaded successfully",
#             "gradeable_id": gradeable_id,
#             "total_submissions": len(scores)
#         })
    
#     except ValueError as ve:
#         db.rollback()
#         raise HTTPException(status_code=400, detail=str(ve))
#     except Exception as e:
#         db.rollback()
#         raise HTTPException(status_code=500, detail=f"Unexpected error uploading scores: {str(e)}")
        
        

@router.post("/gradeables/create")
async def create_gradeable(
    # gradeable: GradeableCreateRequest,
    title: str = FastAPIForm(...),
    max_points: str = FastAPIForm(...),
    file: UploadFile = File(...), # CSV file,
    user_data: User = Depends(prof_or_ta_required),
    db: Session = Depends(get_db)
):
    """Create a new gradeable"""
    username = user_data.get('sub')
    user = db.query(User).filter(User.username == username).first()
    print("2137")
    try:
        print("Title is", title, "Max points is", max_points, "Creator ID is", user.id)
        new_gradeable = Gradeable(
            title=title,
            max_points=int(max_points),
            creator_id=user.id
        )
        
        print("Hello")
        db.add(new_gradeable)
        db.commit()
        db.refresh(new_gradeable)
        print(new_gradeable.id)
        print("HELLO")

        # Read and parse file content
        content = await file.read()
        content_str = content.decode('utf-8')
        scores = parse_scores_from_csv(
            csv_content=content_str, 
            gradeable_id=new_gradeable.id, 
            max_points=new_gradeable.max_points,
            db=db
        )
        gradeable_id = new_gradeable.id
        for score_data in scores:
            existing_submission = db.query(GradeableScores).filter(
                GradeableScores.gradeable_id == gradeable_id,
                GradeableScores.user_id == score_data["user_id"]
            ).first()
            
            if existing_submission:
                existing_submission.score = score_data["score"]
            else:
                new_submission = GradeableScores(
                    user_id=score_data["user_id"],
                    gradeable_id=gradeable_id,
                    score=score_data["score"]
                )
                db.add(new_submission)
        
        db.commit()
        
        return JSONResponse(status_code=201, content={
            "id": new_gradeable.id,
            "title": new_gradeable.title,
            "max_points": int(new_gradeable.max_points),
            "creator_id": new_gradeable.creator_id,
        })
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error creating gradeable: {str(e)}"
        )


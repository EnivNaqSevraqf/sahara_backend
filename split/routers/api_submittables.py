@app.post("/submittables/{submittable_id}/submit")
async def submit_file(
    submittable_id: int,
    file: UploadFile = File(...),  # Now accepts a single file
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Submit a file for a submittable.
    Only one submission per submittable per team is allowed.
    """
    # Get the submittable
    submittable = db.query(Submittable).filter(Submittable.id == submittable_id).first()
    if not submittable:
        raise HTTPException(status_code=404, detail="Submittable not found")

    # Get the user's team
    user = db.query(User).filter(User.id == current_user["user"].id).first()
    team = user.teams[0] if user.teams else None
    if not user or not team:
        raise HTTPException(status_code=400, detail="User must be part of a team to submit")

    # Check if team already has a submission
    existing_submission = db.query(Submission).filter(
        Submission.team_id == team.id,
        Submission.submittable_id == submittable_id
    ).first()

    if existing_submission:
        raise HTTPException(
            status_code=400, 
            detail="Your team has already submitted a file for this submittable. Please delete the existing submission first."
        )

    # Check if submission is allowed based on opens_at and deadline
    now = datetime.now(timezone.utc)
    opens_at = datetime.fromisoformat(submittable.opens_at) if submittable.opens_at else None
    deadline = datetime.fromisoformat(submittable.deadline)

    if opens_at and now < opens_at:
        raise HTTPException(status_code=400, detail="Submission period has not started yet")
    if now > deadline:
        raise HTTPException(status_code=400, detail="Submission deadline has passed")

    # Generate a unique filename
    file_extension = os.path.splitext(file.filename)[1]
    unique_filename = f"submission_{uuid.uuid4()}{file_extension}"
    file_path = os.path.join("uploads", unique_filename)

    # Save the file
    try:
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")

    # Create submission record
    submission = Submission(
        team_id=team.id,
        file_url=file_path,
        original_filename=file.filename,
        submittable_id=submittable_id,
        score=None  # Initialize score as None since it hasn't been graded yet
    )

    try:
        db.add(submission)
        db.commit()
        db.refresh(submission)
        return {
            "message": "File submitted successfully",
            "submission_id": submission.id,
            "original_filename": submission.original_filename,
            "max_score": submittable.max_score,  # Include max_score in response
            "score": submission.score  # Include current score (will be None for new submissions)
        }
    except Exception as e:
        # If database operation fails, delete the uploaded file
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=500, detail=f"Failed to create submission record: {str(e)}")
    

    @app.get("/submissions/{submission_id}/download")
async def download_submission(
    submission_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Download a submission file"""
    try:
        submission = db.query(Submission).filter(Submission.id == submission_id).first()
        if not submission:
            raise HTTPException(status_code=404, detail="Submission not found")
        
        user = current_user["user"]
        role = current_user["role"]
        
        # Check permissions
        if role == RoleType.PROF or role == RoleType.TA:
            # Professors can download any submission
            pass
        elif role == RoleType.STUDENT:
            # Students can only download their team's submission
            team = user.teams[0] if user.teams else None
            if not team.id or team.id != submission.team_id:
                raise HTTPException(status_code=403, detail="Not authorized to download this submission")
        else:
            raise HTTPException(status_code=403, detail="Not authorized to download submissions")
        
        # Get the file path
        local_path = submission.file_url.lstrip('/')
        if not os.path.exists(local_path):
            raise HTTPException(status_code=404, detail="File not found")
        
        # Return the file directly
        return FileResponse(
            local_path,
            filename=submission.original_filename,
            media_type="application/octet-stream"
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error downloading submission: {str(e)}")

# this is to get all submittables categorized by status, done by students and profs
@app.get("/submittables/")
async def get_submittables(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get all submittables categorized by status"""
    try:
        # Get all submittables
        submittables = db.query(Submittable).all()
        
        # Get user's team submissions
        user = current_user["user"]
        team = user.teams[0] if user.teams else None
        if team is None:
            return {
                "team_id": None,
                "upcoming": [],
                "open": [],
                "closed": []
            }
        team_submissions = {}
        if team.id:
            submissions = db.query(Submission).filter(Submission.team_id == team.id).all()
            team_submissions = {s.submittable_id: s for s in submissions}
        
        # Helper function to format submittable
        def format_submittable(s):
            submission = team_submissions.get(s.id)
            return {
                "id": s.id,
                "title": s.title,
                "description": s.description,
                "opens_at": s.opens_at,
                "deadline": s.deadline,
                "max_score": s.max_score,  # Add max_score from submittable
                "reference_files": [{
                    "id": 1,  # Using a placeholder ID for now
                    "original_filename": s.original_filename
                }] if s.file_url else [],
                "submission_status": {
                    "has_submitted": bool(submission),
                    "submission_id": submission.id if submission else None,
                    "submitted_on": submission.submitted_on if submission else None,
                    "original_filename": submission.original_filename if submission else None,
                    "score": submission.score if submission else None  # Add score from submission
                }
            }

        # Categorize submittables
        now = datetime.now(timezone.utc)
        upcoming = []
        open_submittables = []
        closed = []

        for s in submittables:
            formatted = format_submittable(s)
            opens_at = datetime.fromisoformat(s.opens_at) if s.opens_at else None
            deadline = datetime.fromisoformat(s.deadline)

            if opens_at and now < opens_at:
                upcoming.append(formatted)
            elif now > deadline:
                closed.append(formatted)
            else:
                open_submittables.append(formatted)

        return {
            "team_id": team.id,
            "upcoming": upcoming,
            "open": open_submittables,
            "closed": closed
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching submittables: {str(e)}")

@app.get("/submittables/all")
async def get_all_submittables(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get all submittables categorized by status for professors or TAs"""
    try:
        # Check if the user is a professor or TA
        if current_user["role"] not in [RoleType.PROF, RoleType.TA]:
            raise HTTPException(
                status_code=403,
                detail="Only professors or TAs can access this endpoint"
            )

        # Fetch all submittables
        submittables = db.query(Submittable).all()

        # Categorize submittables
        now = datetime.now(timezone.utc)
        upcoming = []
        open_submittables = []
        closed = []

        for submittable in submittables:
            opens_at = datetime.fromisoformat(submittable.opens_at) if submittable.opens_at else None
            deadline = datetime.fromisoformat(submittable.deadline)

            formatted_submittable = {
                "id": submittable.id,
                "title": submittable.title,
                "description": submittable.description,
                "opens_at": submittable.opens_at,
                "deadline": submittable.deadline,
                "max_score": submittable.max_score,
                "created_at": submittable.created_at,
                "reference_files": [{
                    "file_url": submittable.file_url,
                    "original_filename": submittable.original_filename
                }] if submittable.file_url else []
            }

            if opens_at and now < opens_at:
                upcoming.append(formatted_submittable)
            elif now > deadline:
                closed.append(formatted_submittable)
            else:
                open_submittables.append(formatted_submittable)

        # Return categorized submittables
        return {
            "upcoming": upcoming,
            "open": open_submittables,
            "closed": closed
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching submittables: {str(e)}")
    
# this is to download the reference file for a submittable, done by students and profs
@app.get("/submittables/{submittable_id}/reference-files/download")
async def download_reference_file(
    submittable_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Download a reference file for a submittable"""
    try:
        # Get the submittable
        submittable = db.query(Submittable).filter(Submittable.id == submittable_id).first()
        if not submittable:
            raise HTTPException(status_code=404, detail="Submittable not found")

        if not submittable.file_url:
            raise HTTPException(status_code=404, detail="No reference file found")

        # Check if file exists
        if not os.path.exists(submittable.file_url):
            raise HTTPException(status_code=404, detail="File not found on server")

        # Return the file
        return FileResponse(
            submittable.file_url,
            media_type='application/octet-stream',
            filename=submittable.original_filename
        )

    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error downloading file: {str(e)}")

# this is to create a new submittable, done by profs
@app.post("/submittables/create")
async def create_submittable(
    title: str = FastAPIForm(...),
    deadline: str = FastAPIForm(...),
    description: str = FastAPIForm(...),
    max_score: int = FastAPIForm(...),  # Add max_score parameter
    opens_at: Optional[str] = FastAPIForm(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    token: str = Depends(prof_or_ta_required)
):
    """Create a new submittable with a reference file"""
    try:
        # Basic validation
        try:
            deadline_dt = datetime.fromisoformat(deadline.replace('Z', '+00:00'))
            if opens_at:
                opens_at_dt = datetime.fromisoformat(opens_at.replace('Z', '+00:00'))
                # Validate that opens_at is before deadline
                if opens_at_dt >= deadline_dt:
                    raise HTTPException(
                        status_code=400, 
                        detail="opens_at must be before deadline"
                    )
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format")
            
        # Validate max_score
        if max_score <= 0:
            raise HTTPException(status_code=400, detail="Maximum score must be greater than zero")
            
        # Get the creator (professor) from token
        payload = token  # The token is already decoded by prof_required dependency
        username = payload.get("sub")
        user = db.query(User).filter(User.username == username).first()
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Save the reference file
        file_extension = file.filename.split('.')[-1]
        file_name = f"ref_{uuid.uuid4()}.{file_extension}"
        file_path = f"uploads/{file_name}"
        
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Create submittable in database with file information
        new_submittable = Submittable(
            title=title,
            opens_at=opens_at,
            deadline=deadline,
            description=description,
            max_score=max_score,  # Add max_score to submittable creation
            creator_id=user.id,
            file_url=f"uploads/{file_name}",  # URL path without leading slash
            original_filename=file.filename
        )
        
        db.add(new_submittable)
        db.commit()
        db.refresh(new_submittable)

        # Return JSON response with proper structure
        return JSONResponse(
            status_code=201,
            content={
                "message": "Submittable created successfully",
                "submittable": {
                    "id": new_submittable.id,
                    "title": new_submittable.title,
                    "opens_at": new_submittable.opens_at,
                    "deadline": new_submittable.deadline,
                    "description": new_submittable.description,
                    "max_score": new_submittable.max_score,  # Include max_score in response
                    "created_at": new_submittable.created_at,
                    "reference_files": [{
                        "original_filename": new_submittable.original_filename
                    }] if new_submittable.file_url else [],
                    "submission_status": {
                        "has_submitted": False,
                        "submission_id": None,
                        "submitted_on": None,
                        "original_filename": None,
                        "score": None  # Include score field in submission status
                    }
                }
            }
        )

    except HTTPException as he:
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)  # Clean up file if validation fails
        raise he
    except Exception as e:
        db.rollback()
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)  # Clean up file if something went wrong
        raise HTTPException(status_code=500, detail=f"Error creating submittable: {str(e)}")

# this is to get details of a specific submittable, done by students and profs
@app.get("/submittables/{submittable_id}")
async def get_submittable(
    submittable_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get details of a specific submittable"""
    try:
        submittable = db.query(Submittable).filter(Submittable.id == submittable_id).first()
        if not submittable:
            raise HTTPException(status_code=404, detail="Submittable not found")
        
        return JSONResponse(status_code=200, content={
            "id": submittable.id,
            "title": submittable.title,
            "opens_at": submittable.opens_at,
            "deadline": submittable.deadline,
            "description": submittable.description,
            "max_score": submittable.max_score,
            "created_at": submittable.created_at,
            "reference_file": {
                "file_url": submittable.file_url,
                "original_filename": submittable.original_filename
            } if submittable.file_url else None
        })
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching submittable: {str(e)}")

# this is to get all submissions for a submittable, done by profs
@app.get("/submittables/{submittable_id}/submissions")
async def get_submittable_submissions(
    submittable_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get all submissions for a submittable (professors only)"""
    try:
        if current_user["role"] == RoleType.STUDENT:
            raise HTTPException(status_code=403, detail="Only professors can view all submissions")
        
        submittable = db.query(Submittable).filter(Submittable.id == submittable_id).first()
        if not submittable:
            raise HTTPException(status_code=404, detail="Submittable not found")
        
        submissions = db.query(Submission).filter(Submission.submittable_id == submittable_id).all()
        
        result = []
        for submission in submissions:
            submission_data = {
                "id": submission.id,
                "team_id": submission.team_id,
                "submitted_on": submission.submitted_on,
                "score": submission.score,
                "max_score": submittable.max_score,
                "file": {
                    "file_url": submission.file_url,
                    "original_filename": submission.original_filename
                }
            }
            result.append(submission_data)
        
        return JSONResponse(status_code=200, content=result)
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching submissions: {str(e)}")

# this is to delete a submittable and all its submissions, done by profs
@app.delete("/submittables/{submittable_id}")
async def delete_submittable(
    submittable_id: int,
    db: Session = Depends(get_db),
    token: str = Depends(prof_or_ta_required)
):
    """Delete a submittable and all its submissions (professors only)"""
    try:
        submittable = db.query(Submittable).filter(Submittable.id == submittable_id).first()
        if not submittable:
            raise HTTPException(status_code=404, detail="Submittable not found")
        
        # Delete the reference file if it exists
        if submittable.file_url:
            local_path = submittable.file_url.lstrip('/')
            if os.path.exists(local_path):
                os.remove(local_path)
        
        # Delete all submission files
        submissions = db.query(Submission).filter(Submission.submittable_id == submittable_id).all()
        for submission in submissions:
            if submission.file_url:
                local_path = submission.file_url.lstrip('/')
                if os.path.exists(local_path):
                    os.remove(local_path)
        
        # Delete all submissions
        db.query(Submission).filter(Submission.submittable_id == submittable_id).delete()
        
        # Delete the submittable
        db.delete(submittable)
        db.commit()
        
        return JSONResponse(status_code=200, content={"message": "Submittable deleted successfully"})
    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error deleting submittable: {str(e)}")

# this is to update a submittable, done by profs
@app.put("/submittables/{submittable_id}")
async def update_submittable(
    submittable_id: int,
    title: str = FastAPIForm(...),
    deadline: str = FastAPIForm(...),
    description: str = FastAPIForm(...),
    opens_at: Optional[str] = FastAPIForm(None),
    file: Optional[UploadFile] = None,
    db: Session = Depends(get_db),
    token: str = Depends(prof_or_ta_required)
):
    """Update a submittable (professors only)"""
    try:
        # Basic validation
        try:
            deadline_dt = datetime.fromisoformat(deadline.replace('Z', '+00:00'))
            if opens_at:
                opens_at_dt = datetime.fromisoformat(opens_at.replace('Z', '+00:00'))
                # Validate that opens_at is before deadline
                if opens_at_dt >= deadline_dt:
                    raise HTTPException(
                        status_code=400, 
                        detail="opens_at must be before deadline"
                    )
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format")
            
            
        existing_submittable = db.query(Submittable).filter(Submittable.id == submittable_id).first()
        if not existing_submittable:
            raise HTTPException(status_code=404, detail="Submittable not found")
        
        # Update basic information
        existing_submittable.title = title
        existing_submittable.opens_at = opens_at
        existing_submittable.deadline = deadline
        existing_submittable.description = description
        
        # Handle file update if provided
        if file:
            # Delete old file if it exists
            if existing_submittable.file_url:
                old_file_path = existing_submittable.file_url.lstrip('/')
                if os.path.exists(old_file_path):
                    os.remove(old_file_path)
            
            # Save new file
            file_extension = file.filename.split('.')[-1]
            file_name = f"ref_{uuid.uuid4()}.{file_extension}"
            file_path = f"uploads/{file_name}"
            
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            
            existing_submittable.file_url = f"uploads/{file_name}"
            existing_submittable.original_filename = file.filename
        
        db.commit()
        db.refresh(existing_submittable)
        
        return JSONResponse(status_code=200, content={
            "message": "Submittable updated successfully",
            "submittable_id": existing_submittable.id
        })
    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)  # Clean up file if something went wrong
        raise HTTPException(status_code=500, detail=f"Error updating submittable: {str(e)}")
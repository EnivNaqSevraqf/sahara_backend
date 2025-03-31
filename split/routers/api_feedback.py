@app.get("/feedback/students")
async def get_student_feedback_info(
    current_user: dict = Depends(get_current_user),
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
                "is_current_user": member.id == user.id
            }
            for member in team.members
        ]

        if len(team_members) <= 1:
            raise HTTPException(
                status_code=400,
                detail="No team members found to provide feedback for"
            )

        # Check if user has already submitted feedback
        existing_submission = db.query(FeedbackSubmission).filter(
            FeedbackSubmission.submitter_id == user.id,
            FeedbackSubmission.team_id == team.id
        ).first()

        # If there's an existing submission, include the feedback details
        submitted_feedback = None
        if existing_submission:
            feedback_details = db.query(FeedbackDetail).filter(
                FeedbackDetail.submission_id == existing_submission.id
            ).all()
            
            submitted_feedback = {
                "submission_id": existing_submission.id,
                "submitted_at": existing_submission.submitted_at.isoformat(),
                "details": [
                    {
                        "member_id": detail.member_id,
                        "contribution": detail.contribution,
                        "remarks": detail.remarks
                    }
                    for detail in feedback_details
                ]
            }

        return {
            "team_id": team.id,
            "team_name": team.name,
            "members": team_members,
            "submitted_feedback": submitted_feedback
        }
        
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/feedback/student/submit")
async def submit_student_feedback(
    feedback: FeedbackSubmissionRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Submit feedback for team members"""
    try:
        user = current_user["user"]
        
        # Check if user is a student
        if current_user["role"] != RoleType.STUDENT:
            raise HTTPException(
                status_code=403,
                detail="Only students can submit feedback"
            )

        # Check if user belongs to the team they're submitting feedback for
        if not any(team.id == feedback.team_id for team in user.teams):
            raise HTTPException(
                status_code=403,
                detail="You can only submit feedback for your own team"
            )

        # Check if user has already submitted feedback
        existing_submission = db.query(FeedbackSubmission).filter(
            FeedbackSubmission.submitter_id == user.id,
            FeedbackSubmission.team_id == feedback.team_id
        ).first()

        if existing_submission:
            raise HTTPException(
                status_code=400,
                detail="You have already submitted feedback for this team"
            )

        # Validate that all team members are being rated (except the submitter)
        team = next(team for team in user.teams if team.id == feedback.team_id)
        expected_member_count = len(team.members)  # Exclude the submitter
        if len(feedback.details) != expected_member_count:
            raise HTTPException(
                status_code=400,
                detail="Feedback must be provided for all team members"
            )

        # Validate that the rated members are actually in the team
        team_member_ids = {member.id for member in team.members}
        submitted_member_ids = {detail.member_id for detail in feedback.details}
        if team_member_ids != submitted_member_ids:
            raise HTTPException(
                status_code=400,
                detail="Feedback can only be provided for current team members"
            )

        # Validate total contribution equals 100%
        total_contribution = sum(detail.contribution for detail in feedback.details)
        if total_contribution != 100:
            raise HTTPException(
                status_code=400,
                detail="Total contribution must equal 100%"
            )

        # Create feedback submission
        new_submission = FeedbackSubmission(
            submitter_id=user.id,
            team_id=feedback.team_id,
            submitted_at=datetime.now(timezone.utc)
        )
        db.add(new_submission)
        db.flush()  # Get the ID before committing

        # Create feedback details
        for detail in feedback.details:
            new_detail = FeedbackDetail(
                submission_id=new_submission.id,
                member_id=detail.member_id,
                contribution=detail.contribution,
                remarks=detail.remarks
            )
            db.add(new_detail)

        db.commit()
        return {"message": "Feedback submitted successfully"}
    except HTTPException as he:
        db.rollback()
        raise he
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/feedback/admin")
async def get_admin_feedback(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all teams that have at least one feedback submission"""
    try:
        # Check if user is an admin (TA or professor)
        if current_user["role"] not in [RoleType.TA, RoleType.PROF]:
            raise HTTPException(
                status_code=403,
                detail="Only teaching assistants and professors can access this endpoint"
            )

        # Get all teams that have feedback submissions
        teams_with_feedback = (
            db.query(Team)
            .join(FeedbackSubmission, Team.id == FeedbackSubmission.team_id)
            .distinct()
            .all()
        )

        result = []
        for team in teams_with_feedback:
            # Get submission count for this team
            submission_count = (
                db.query(FeedbackSubmission)
                .filter(FeedbackSubmission.team_id == team.id)
                .count()
            )

            result.append({
                "team_id": team.id,
                "team_name": team.name,
                "member_count": len(team.members),
                "submission_count": submission_count,
                "last_submission": db.query(FeedbackSubmission)
                    .filter(FeedbackSubmission.team_id == team.id)
                    .order_by(FeedbackSubmission.submitted_at.desc())
                    .first()
                    .submitted_at.isoformat()
            })

        return result
        
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/feedback/admin/view/{team_id}")
async def get_team_feedback_details(
    team_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get detailed feedback submissions for a specific team"""
    try:
        # Check if user is an admin (TA or professor)
        if current_user["role"] not in [RoleType.TA, RoleType.PROF]:
            raise HTTPException(
                status_code=403,
                detail="Only teaching assistants and professors can access this endpoint"
            )

        # Check if team exists
        team = db.query(Team).filter(Team.id == team_id).first()
        if not team:
            raise HTTPException(status_code=404, detail="Team not found")

        # Get all feedback submissions for this team
        submissions = (
            db.query(FeedbackSubmission)
            .filter(FeedbackSubmission.team_id == team_id)
            .all()
        )

        # Get all team members for reference
        team_members = {
            member.id: member.name 
            for member in team.members
        }

        # Format the submissions with detailed information
        formatted_submissions = []
        for submission in submissions:
            # Get details for this submission
            feedback_details = (
                db.query(FeedbackDetail)
                .filter(FeedbackDetail.submission_id == submission.id)
                .all()
            )

            # Get submitter info
            submitter = db.query(User).filter(User.id == submission.submitter_id).first()

            formatted_submissions.append({
                "submission_id": submission.id,
                "submitter": {
                    "id": submitter.id,
                    "name": submitter.name
                },
                "submitted_at": submission.submitted_at.isoformat(),
                "feedback": [
                    {
                        "member_id": detail.member_id,
                        "member_name": team_members.get(detail.member_id, "Unknown"),
                        "contribution": detail.contribution,
                        "remarks": detail.remarks
                    }
                    for detail in feedback_details
                ]
            })

        return {
            "team_id": team.id,
            "team_name": team.name,
            "members": team_members,
            "submissions": formatted_submissions
        }

    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/feedback/students")
async def get_student_feedback_info(
    current_user: dict = Depends(get_current_user),
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
                "is_current_user": member.id == user.id
            }
            for member in team.members
        ]

        if len(team_members) <= 1:
            raise HTTPException(
                status_code=400,
                detail="No team members found to provide feedback for"
            )

        # Check if user has already submitted feedback
        existing_submission = db.query(FeedbackSubmission).filter(
            FeedbackSubmission.submitter_id == user.id,
            FeedbackSubmission.team_id == team.id
        ).first()

        # If there's an existing submission, include the feedback details
        submitted_feedback = None
        if existing_submission:
            feedback_details = db.query(FeedbackDetail).filter(
                FeedbackDetail.submission_id == existing_submission.id
            ).all()
            
            submitted_feedback = {
                "submission_id": existing_submission.id,
                "submitted_at": existing_submission.submitted_at.isoformat(),
                "details": [
                    {
                        "member_id": detail.member_id,
                        "contribution": detail.contribution,
                        "remarks": detail.remarks
                    }
                    for detail in feedback_details
                ]
            }

        return {
            "team_id": team.id,
            "team_name": team.name,
            "members": team_members,
            "submitted_feedback": submitted_feedback
        }
        
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/feedback/student/submit")
async def submit_student_feedback(
    feedback: FeedbackSubmissionRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Submit feedback for team members"""
    try:
        user = current_user["user"]
        
        # Check if user is a student
        if current_user["role"] != RoleType.STUDENT:
            raise HTTPException(
                status_code=403,
                detail="Only students can submit feedback"
            )

        # Check if user belongs to the team they're submitting feedback for
        if not any(team.id == feedback.team_id for team in user.teams):
            raise HTTPException(
                status_code=403,
                detail="You can only submit feedback for your own team"
            )

        # Check if user has already submitted feedback
        existing_submission = db.query(FeedbackSubmission).filter(
            FeedbackSubmission.submitter_id == user.id,
            FeedbackSubmission.team_id == feedback.team_id
        ).first()

        if existing_submission:
            raise HTTPException(
                status_code=400,
                detail="You have already submitted feedback for this team"
            )

        # Validate that all team members are being rated (except the submitter)
        team = next(team for team in user.teams if team.id == feedback.team_id)
        expected_member_count = len(team.members)  # Exclude the submitter
        if len(feedback.details) != expected_member_count:
            raise HTTPException(
                status_code=400,
                detail="Feedback must be provided for all team members"
            )

        # Validate that the rated members are actually in the team
        team_member_ids = {member.id for member in team.members}
        submitted_member_ids = {detail.member_id for detail in feedback.details}
        if team_member_ids != submitted_member_ids:
            raise HTTPException(
                status_code=400,
                detail="Feedback can only be provided for current team members"
            )

        # Validate total contribution equals 100%
        total_contribution = sum(detail.contribution for detail in feedback.details)
        if total_contribution != 100:
            raise HTTPException(
                status_code=400,
                detail="Total contribution must equal 100%"
            )

        # Create feedback submission
        new_submission = FeedbackSubmission(
            submitter_id=user.id,
            team_id=feedback.team_id,
            submitted_at=datetime.now(timezone.utc)
        )
        db.add(new_submission)
        db.flush()  # Get the ID before committing

        # Create feedback details
        for detail in feedback.details:
            new_detail = FeedbackDetail(
                submission_id=new_submission.id,
                member_id=detail.member_id,
                contribution=detail.contribution,
                remarks=detail.remarks
            )
            db.add(new_detail)

        db.commit()
        return {"message": "Feedback submitted successfully"}
    except HTTPException as he:
        db.rollback()
        raise he
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/feedback/admin")
async def get_admin_feedback(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all teams that have at least one feedback submission"""
    try:
        # Check if user is an admin (TA or professor)
        if current_user["role"] not in [RoleType.TA, RoleType.PROF]:
            raise HTTPException(
                status_code=403,
                detail="Only teaching assistants and professors can access this endpoint"
            )

        # Get all teams that have feedback submissions
        teams_with_feedback = (
            db.query(Team)
            .join(FeedbackSubmission, Team.id == FeedbackSubmission.team_id)
            .distinct()
            .all()
        )

        result = []
        for team in teams_with_feedback:
            # Get submission count for this team
            submission_count = (
                db.query(FeedbackSubmission)
                .filter(FeedbackSubmission.team_id == team.id)
                .count()
            )

            result.append({
                "team_id": team.id,
                "team_name": team.name,
                "member_count": len(team.members),
                "submission_count": submission_count,
                "last_submission": db.query(FeedbackSubmission)
                    .filter(FeedbackSubmission.team_id == team.id)
                    .order_by(FeedbackSubmission.submitted_at.desc())
                    .first()
                    .submitted_at.isoformat()
            })

        return result
        
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/feedback/admin/view/{team_id}")
async def get_team_feedback_details(
    team_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get detailed feedback submissions for a specific team"""
    try:
        # Check if user is an admin (TA or professor)
        if current_user["role"] not in [RoleType.TA, RoleType.PROF]:
            raise HTTPException(
                status_code=403,
                detail="Only teaching assistants and professors can access this endpoint"
            )

        # Check if team exists
        team = db.query(Team).filter(Team.id == team_id).first()
        if not team:
            raise HTTPException(status_code=404, detail="Team not found")

        # Get all feedback submissions for this team
        submissions = (
            db.query(FeedbackSubmission)
            .filter(FeedbackSubmission.team_id == team_id)
            .all()
        )

        # Get all team members for reference
        team_members = {
            member.id: member.name 
            for member in team.members
        }

        # Format the submissions with detailed information
        formatted_submissions = []
        for submission in submissions:
            # Get details for this submission
            feedback_details = (
                db.query(FeedbackDetail)
                .filter(FeedbackDetail.submission_id == submission.id)
                .all()
            )

            # Get submitter info
            submitter = db.query(User).filter(User.id == submission.submitter_id).first()

            formatted_submissions.append({
                "submission_id": submission.id,
                "submitter": {
                    "id": submitter.id,
                    "name": submitter.name
                },
                "submitted_at": submission.submitted_at.isoformat(),
                "feedback": [
                    {
                        "member_id": detail.member_id,
                        "member_name": team_members.get(detail.member_id, "Unknown"),
                        "contribution": detail.contribution,
                        "remarks": detail.remarks
                    }
                    for detail in feedback_details
                ]
            })

        return {
            "team_id": team.id,
            "team_name": team.name,
            "members": team_members,
            "submissions": formatted_submissions
        }

    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
from fastapi import FastAPI, Depends, status, Response, HTTPException, UploadFile, File, Form
from typing import Optional, List
from pydantic import BaseModel
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy import Column, Integer, String
import schemas, models
from database import engine, SessionLocal
import shutil
import uuid
import json
import os
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

models.Base.metadata.create_all(engine)

def get_db():
    db=SessionLocal()
    try:
        yield db
    finally:
        db.close()

# @app.post('/announcements', status_code=status.HTTP_201_CREATED)
# async def create(request: schemas.Announcements, db: Session = Depends(get_db)):
#     new=models.Announcements(title=request.title, description=request.description)
#     db.add(new)
#     db.commit()
#     db.refresh(new)
#     return new

@app.post('/announcements', status_code=status.HTTP_201_CREATED)
async def create(title: str=Form(...), description: str=Form(...), file: UploadFile = File(None), db: Session = Depends(get_db)):
    file_location = None
    if file:
        file_extension = file.filename.split('.')[-1]
        file_name = f"{uuid.uuid4()}.{file_extension}"
        file_location = f"uploads/{file_name}"
        with open(file_location, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

    try:
        description_json = json.loads(description)
    except json.JSONDecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON for description")
    print(file_location)
    new_announcement = models.Announcements(
        title=title,
        description=description_json,
        file_path=file_location
    )
    db.add(new_announcement)
    db.commit()
    db.refresh(new_announcement)
    return new_announcement


@app.delete('/announcements/{id}', status_code=status.HTTP_204_NO_CONTENT)
def destroy(id:int, db:Session=Depends(get_db)):
    blog=db.query(models.Announcements).filter(models.Announcements.id==id)
    if not blog.first():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f'Announcement with id: {id} not found')
    if blog.first().file_path and os.path.exists(blog.first().file_path):
        os.remove(blog.first().file_path)
    blog.delete(synchronize_session=False)
    db.commit()
    return 'done'

@app.put('/announcements/{id}', status_code=status.HTTP_202_ACCEPTED)
def update(id:int, title:str=Form(...), description:str=Form(...), file: UploadFile=File(None), db: Session=Depends(get_db)):
    blog=db.query(models.Announcements).filter(models.Announcements.id==id)
    if not blog.first():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f'Announcement with id: {id} not found')
    new_file_path=blog.first().file_path
    if file:
        if blog.first().file_path and os.path.exists(blog.first().file_path):
            os.remove(blog.first().file_path)
        
        file_extension = file.filename.split('.')[-1]
        file_name = f"{uuid.uuid4()}.{file_extension}"
        new_file_path = f"uploads/{file_name}"
        with open(new_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    
    try:
        description_json = json.loads(description)
    except json.JSONDecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON for description")
    
    # Update announcement fields
    blog.first().title = title
    blog.first().description = description_json
    blog.first().file_path = new_file_path

    db.commit()
    db.refresh(blog.first())
    return {"detail": "Announcement updated", "announcement": blog.first()}

@app.get('/announcements', response_model=List[schemas.Show])
def all(db:Session = Depends(get_db)):
    blogs = db.query(models.Announcements).all()
    return blogs

@app.get('/announcements/{id}', status_code=200, response_model=schemas.Show)
def show(id, response: Response, db:Session=Depends(get_db)):
    blog = db.query(models.Announcements).filter(models.Announcements.id==id).first()
    if not blog:
        response.status_code=status.HTTP_404_NOT_FOUND
        return {'details': f'blog with {id} not found'}
    return blog

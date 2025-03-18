from fastapi import FastAPI, Depends, status, Response, HTTPException
from typing import Optional
from pydantic import BaseModel
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy import Column, Integer, String
import schemas, models
from database import engine, SessionLocal
app = FastAPI()

models.Base.metadata.create_all(engine)

def get_db():
    db=SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.post('/announcements', status_code=status.HTTP_201_CREATED)
def create(request: schemas.Announcements, db: Session = Depends(get_db)):
    new=models.Announcements(title=request.title, description=request.description)
    db.add(new)
    db.commit()
    db.refresh(new)
    return new

@app.delete('/announcements/{id}', status_code=status.HTTP_204_NO_CONTENT)
def destroy(id, db:Session=Depends(get_db)):
    blog=db.query(models.Announcements).filter(models.Announcements.id==id)
    if not blog.first():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f'Announcement with id: {id} not found')
    
    blog.delete(synchronize_session=False)
    db.commit()
    return 'done'

@app.put('/announcements/{id}', status_code=status.HTTP_202_ACCEPTED)
def update(id, request:schemas.Announcements, db: Session=Depends(get_db)):
    blog=db.query(models.Announcements).filter(models.Announcements.id==id)
    if not blog.first():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f'Announcement with id: {id} not found')
    
    blog.update(request)
    db.commit()
    return 'updated'

@app.get('/announcements')
def all(db:Session = Depends(get_db)):
    blogs = db.query(models.Announcements).all()
    return blogs

@app.get('/announcements/{id}', status_code=200)
def show(id, response: Response, db:Session=Depends(get_db)):
    blog = db.query(models.Announcements).filter(models.Announcements.id==id).first()
    if not blog:
        response.status_code=status.HTTP_404_NOT_FOUND
        return {'details': f'blog with {id} not found'}
    return blog
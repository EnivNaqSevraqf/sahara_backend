from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from ..config.config import DATABASE_URL, SessionLocal  #DATABASE_URL is stored in config/config.py

# Define the Base class for ORM models to inherit from
Base = declarative_base()

# Create the engine to connect to your PostgreSQL database
engine = create_engine(DATABASE_URL)

# Create a configured "SessionLocal" class


# Dependency for getting a database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

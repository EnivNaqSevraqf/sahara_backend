from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Database setup - postgres
DATABASE_URL = "postgresql://avnadmin:AVNS_DkrVvzHCnOiMVJwagav@pg-8b6fabf-sahara-team-8.f.aivencloud.com:17950/defaultdb"

# Create engine
engine = create_engine(DATABASE_URL)

# Create session
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
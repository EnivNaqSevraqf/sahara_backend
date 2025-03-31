from passlib.context import CryptContext
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
DATABASE_URL = "postgresql://avnadmin:AVNS_YfDPPydQ-Ax7FLzuLkD@pg-b1db5cd-sahara-raf.f.aivencloud.com:12051/defaultdb?sslmode=require"
SECRET_KEY = "a3eca18b09973b1890cfbc94d5322c1aae378b73ea5eee0194ced065175d04aa"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
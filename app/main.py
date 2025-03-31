from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
import os
import time
from typing import Callable
from redis.asyncio import Redis

from app.db.base import Base
from app.db.session import engine, SessionLocal
from app.db.init_db import init_db
from app.routers import auth, chat, feedback, forms, submissions, teams, users
from app.core.config.settings import get_settings
from app.core.config.logging_config import setup_logging

# Setup logging
logger = setup_logging()

# Create necessary directories
os.makedirs("uploads", exist_ok=True)
os.makedirs("forums_uploads", exist_ok=True)
os.makedirs("static", exist_ok=True)

# Initialize FastAPI app
app = FastAPI(
    title=get_settings().PROJECT_NAME,
    openapi_url=f"{get_settings().API_V1_PREFIX}/openapi.json",
    docs_url=f"{get_settings().API_V1_PREFIX}/docs",
    redoc_url=f"{get_settings().API_V1_PREFIX}/redoc",
)

# Redis connection instance
redis = None

@app.on_event("startup")
async def startup_event():
    global redis
    # Initialize Redis if URL is configured
    if get_settings().REDIS_URL:
        try:
            redis = Redis.from_url(
                get_settings().REDIS_URL,
                encoding="utf-8",
                decode_responses=True
            )
            await redis.ping()
            logger.info("Redis connection established")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {str(e)}")
    
    # Initialize database
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        init_db(db)
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization failed: {str(e)}")
    finally:
        db.close()

@app.on_event("shutdown")
async def shutdown_event():
    global redis
    if redis:
        await redis.close()
        logger.info("Redis connection closed")

# Middleware for request logging
@app.middleware("http")
async def log_requests(request: Request, call_next: Callable):
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time
    logger.info(
        f"Method: {request.method} Path: {request.url.path} "
        f"Status: {response.status_code} Duration: {duration:.2f}s"
    )
    return response

# Rate limiting middleware
@app.middleware("http")
async def rate_limit(request: Request, call_next: Callable):
    if redis:
        client_ip = request.client.host
        key = f"rate_limit:{client_ip}"
        requests = await redis.incr(key)
        
        if requests == 1:
            await redis.expire(key, 60)  # Reset after 60 seconds
        
        if requests > 100:  # 100 requests per minute limit
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"detail": "Too many requests"}
            )
    
    return await call_next(request)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static directories
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
app.mount("/forums_uploads", StaticFiles(directory="forums_uploads"), name="forums_uploads")

# Include routers with prefix
api_prefix = get_settings().API_V1_PREFIX
app.include_router(auth.router, prefix=api_prefix)
app.include_router(chat.router, prefix=api_prefix)
app.include_router(feedback.router, prefix=api_prefix)
app.include_router(forms.router, prefix=api_prefix)
app.include_router(submissions.router, prefix=api_prefix)
app.include_router(teams.router, prefix=api_prefix)
app.include_router(users.router, prefix=api_prefix)

# Exception handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    logger.error(f"HTTP Exception: {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled Exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )

# Health check endpoint with additional status info
@app.get("/health")
async def health_check():
    status_info = {
        "status": "healthy",
        "timestamp": time.time(),
        "database": "connected",
        "redis": "connected" if redis else "not configured"
    }
    
    # Check database connection
    try:
        db = SessionLocal()
        db.execute("SELECT 1")
        db.close()
    except Exception as e:
        status_info["database"] = "disconnected"
        status_info["status"] = "unhealthy"
        logger.error(f"Database health check failed: {str(e)}")
    
    # Check Redis connection if configured
    if redis:
        try:
            await redis.ping()
        except Exception as e:
            status_info["redis"] = "disconnected"
            status_info["status"] = "unhealthy"
            logger.error(f"Redis health check failed: {str(e)}")
    
    return status_info
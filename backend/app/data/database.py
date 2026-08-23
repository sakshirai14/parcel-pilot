import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from backend.app.config import DATABASE_URL, DATABASE_PATH

# Ensure parent directory of database path exists
DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

# Create Engine
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base model class
Base = declarative_base()

def get_db():
    """
    Dependency to obtain database session.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

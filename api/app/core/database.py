import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Read DB URL from environment, fallback to local SQLite for quick testing
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./carbonlens.db")

# For PostgreSQL, connect args are sometimes needed
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
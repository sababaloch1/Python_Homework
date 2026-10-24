
import os
from urllib.parse import quote_plus

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Build the database URL safely.
db_host = os.getenv("DB_HOST")

if db_host:
    db_port = os.getenv("DB_PORT", "5432")
    db_user = quote_plus(os.getenv("POSTGRES_USER", "postgres"))
    db_password = quote_plus(os.getenv("POSTGRES_PASSWORD", "postgres"))
    db_name = quote_plus(os.getenv("POSTGRES_DB", "carbonlens"))

    DATABASE_URL = (
        f"postgresql+psycopg://{db_user}:{db_password}"
        f"@{db_host}:{db_port}/{db_name}"
    )
else:
    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        "sqlite:///./carbonlens.db",
    )

connect_args = (
    {"check_same_thread": False}
    if DATABASE_URL.startswith("sqlite")
    else {}
)

engine = create_engine(DATABASE_URL, connect_args=connect_args)

# Required by Alembic and SQLAlchemy models.
Base = declarative_base()

# Database session factory.
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

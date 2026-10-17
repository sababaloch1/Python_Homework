import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from api.app.main import app
from api.app.core.database import Base, get_db

# Use an in-memory SQLite database for fast tests
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Override the database dependency
def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

@pytest.fixture(scope="module")
def client():
    # Create the tables in the test database
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as c:
        yield c
    # Drop the tables after tests are done
    Base.metadata.drop_all(bind=engine)
from datetime import datetime, timedelta
from typing import Any, Union
from jose import jwt
import bcrypt
import os

# In production, this MUST be in a .env file
SECRET_KEY = os.getenv("JWT_SECRET", "dpziWNKClU4E2DGQ5vxTcO3BJkP9IXwusRjyb0q8rZSfnYmtLHeM716FhVaAog")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60  # NFR-1.03: Tokens expire after 60 minutes

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Checks if the provided password matches the stored hash."""
    try:
        return bcrypt.checkpw(
            plain_password.encode('utf-8'), 
            hashed_password.encode('utf-8')
        )
    except ValueError:
        return False

def get_password_hash(password: str) -> str:
    """Hashes a password using bcrypt."""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')

def create_access_token(subject: Union[str, Any], org_id: str, role: str) -> str:
    """Creates a JWT access token containing user ID, org_id, and role."""
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {
        "exp": expire, 
        "sub": str(subject), 
        "org_id": str(org_id), 
        "role": role
    }
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt
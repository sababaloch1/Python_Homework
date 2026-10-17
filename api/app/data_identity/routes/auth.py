from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from api.app.core.database import get_db
from api.app.core.models import User, Organization
from api.app.core.security import get_password_hash, verify_password, create_access_token
from api.app.core.enums import UserRole
from api.app.data_identity.schemas import UserRegister, UserResponse, Token

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(user_in: UserRegister, db: Session = Depends(get_db)):
    # 1. Check if user exists
    if db.query(User).filter(User.email == user_in.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # 2. Create the Organization
    new_org = Organization(name=user_in.org_name)
    db.add(new_org)
    db.commit()
    db.refresh(new_org)

    # 3. Create the first User as Admin
    new_user = User(
        org_id=new_org.id,
        email=user_in.email,
        password_hash=get_password_hash(user_in.password),
        full_name=user_in.full_name,
        role=UserRole.admin
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    return new_user

@router.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Generate JWT (NFR-1.03: expires in 60 mins)
    access_token = create_access_token(
        subject=user.id, 
        org_id=user.org_id, 
        role=user.role.value
    )
    return {"access_token": access_token, "token_type": "bearer"}
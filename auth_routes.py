from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel
from auth import create_access_token, verify_password, get_password_hash
from datetime import timedelta
import os

router = APIRouter(prefix="/auth", tags=["authentication"])

# 기본 사용자 정보 (실제 환경에서는 데이터베이스에 저장)
USERS_DB = {
    "admin": {
        "username": "admin",
        "hashed_password": get_password_hash("admin123"),  # 기본 패스워드
        "role": "admin"
    }
}

class Token(BaseModel):
    access_token: str
    token_type: str

class UserLogin(BaseModel):
    username: str
    password: str

security = HTTPBasic()

def authenticate_user(username: str, password: str):
    user = USERS_DB.get(username)
    if not user:
        return False
    if not verify_password(password, user["hashed_password"]):
        return False
    return user

@router.post("/login", response_model=Token)
async def login(user_data: UserLogin):
    user = authenticate_user(user_data.username, user_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=30)
    access_token = create_access_token(
        data={"sub": user["username"], "role": user["role"]}, 
        expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/api-key")
async def get_api_key(credentials: HTTPBasicCredentials = Depends(security)):
    # 기본 인증으로 API 키 발급
    user = authenticate_user(credentials.username, credentials.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password"
        )
    
    # 간단한 API 키 생성 (실제로는 더 복잡한 키 생성 로직 사용)
    api_key = f"besco_{user['username']}_{hash(user['username'])}"
    return {"api_key": api_key, "message": "Use this API key in Authorization header as 'Bearer {api_key}'"}

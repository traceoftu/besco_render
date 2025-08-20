from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()

# PostgreSQL 연결 설정
SQLALCHEMY_DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "postgresql://neondb_owner:npg_6SYPds4TMOmL@ep-fragrant-silence-a1qyugnz-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
)

# 엔진 생성 시 연결 풀과 타임아웃 설정 추가
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_size=5,
    max_overflow=10,
    pool_timeout=30,
    pool_recycle=1800,
    pool_pre_ping=True,  # 연결이 유효한지 확인
    echo=False  # 프로덕션에서는 SQL 로깅 비활성화
)

# 세션 설정
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# 데이터베이스 세션 의존성
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

#!/usr/bin/env python3
"""
BlendComponent 테이블 생성을 위한 마이그레이션 스크립트
"""

import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

def create_blend_components_table():
    """BlendComponent 테이블 생성"""
    
    # 데이터베이스 URL 가져오기
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL 환경변수가 설정되지 않았습니다.")
        return False
    
    try:
        engine = create_engine(database_url)
        
        # BlendComponent 테이블 생성 SQL
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS blend_components (
            id SERIAL PRIMARY KEY,
            blend_id INTEGER NOT NULL REFERENCES materials(id) ON DELETE CASCADE,
            component_id INTEGER NOT NULL REFERENCES materials(id) ON DELETE CASCADE,
            ratio FLOAT NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
        
        CREATE INDEX IF NOT EXISTS idx_blend_components_blend_id ON blend_components(blend_id);
        CREATE INDEX IF NOT EXISTS idx_blend_components_component_id ON blend_components(component_id);
        """
        
        with engine.connect() as conn:
            # 트랜잭션 시작
            trans = conn.begin()
            try:
                # 테이블 생성
                conn.execute(text(create_table_sql))
                trans.commit()
                print("✅ blend_components 테이블이 성공적으로 생성되었습니다.")
                return True
                
            except Exception as e:
                trans.rollback()
                print(f"❌ 테이블 생성 중 오류 발생: {e}")
                return False
                
    except Exception as e:
        print(f"❌ 데이터베이스 연결 오류: {e}")
        return False

def check_table_exists():
    """테이블 존재 여부 확인"""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        return False
    
    try:
        engine = create_engine(database_url)
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'blend_components'
                );
            """))
            exists = result.scalar()
            return exists
    except Exception as e:
        print(f"테이블 확인 중 오류: {e}")
        return False

if __name__ == "__main__":
    print("🔄 BlendComponent 테이블 마이그레이션을 시작합니다...")
    
    # 테이블 존재 여부 확인
    if check_table_exists():
        print("ℹ️  blend_components 테이블이 이미 존재합니다.")
    else:
        print("📝 blend_components 테이블을 생성합니다...")
        if create_blend_components_table():
            print("✅ 마이그레이션이 완료되었습니다.")
        else:
            print("❌ 마이그레이션이 실패했습니다.")

# BESCO API 보안 설정 가이드

## 🔐 구현된 보안 기능

### 1. API 키 인증 시스템
- **위치**: `auth.py`, `auth_routes.py`
- **기능**: Bearer 토큰 방식의 API 키 인증
- **사용법**: 
  ```bash
  # API 키 발급
  curl -X POST "http://localhost:8000/auth/api-key" \
    -u "admin:admin123"
  
  # API 호출
  curl -H "Authorization: Bearer your-api-key" \
    "http://localhost:8000/customers/"
  ```

### 2. CORS 설정
- **위치**: `main.py`
- **기능**: Cross-Origin Resource Sharing 허용
- **현재 설정**: 모든 도메인 허용 (프로덕션에서는 제한 필요)

### 3. JWT 토큰 지원
- **위치**: `auth.py`
- **기능**: JSON Web Token 생성 및 검증
- **만료시간**: 30분

## 🚀 사용 방법

### 1단계: 환경 변수 설정
```bash
# .env 파일 생성
DATABASE_URL=your-postgresql-url
SECRET_KEY=your-secret-key-change-this
API_KEYS=besco_admin_12345,your-custom-key
```

### 2단계: API 키 발급
```bash
# 기본 계정: admin / admin123
POST /auth/api-key
Authorization: Basic admin:admin123
```

### 3단계: 보안된 API 호출
```bash
GET /customers/
Authorization: Bearer your-api-key
```

## ⚙️ 보안 레벨 선택

### 옵션 1: API 키만 사용 (권장)
- 간단하고 효과적
- 현재 구현된 상태
- 대부분의 내부 API에 적합

### 옵션 2: JWT 토큰 사용
- 더 정교한 인증
- 만료시간 관리
- 사용자 세션 관리 필요

### 옵션 3: 보안 없음 (개발용만)
- `verify_api_key` 의존성 제거
- 개발/테스트 환경에서만 사용

## 🔧 추가 보안 강화 방안

1. **Rate Limiting**: slowapi 패키지 사용
2. **HTTPS 강제**: 프로덕션 환경에서 필수
3. **입력 검증 강화**: Pydantic 스키마 확장
4. **로깅 시스템**: 보안 이벤트 기록
5. **IP 화이트리스트**: 특정 IP만 접근 허용

## 🚨 주의사항

1. **SECRET_KEY**: 반드시 강력한 키로 변경
2. **API_KEYS**: 정기적으로 갱신
3. **CORS**: 프로덕션에서는 특정 도메인만 허용
4. **에러 메시지**: 상세 정보 노출 방지
5. **환경 변수**: .env 파일을 git에 커밋하지 말 것

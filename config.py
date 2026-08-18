import os
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

NCP_CLIENT_ID = os.getenv("NAVER_CLIENT_ID")
NCP_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# 필수 환경변수 누락 검증 (앱 시작 시 빠르게 에러를 잡기 위함)
if not all([NCP_CLIENT_ID, NCP_CLIENT_SECRET, GEMINI_API_KEY]):
    raise ValueError("⚠️ .env 파일에 API 키가 누락되었습니다! 설정을 확인하세요.")
import requests
from config import DISCORD_WEBHOOK_URL

def send_discord_alert(keyword, overview, indicators, filename):
    """디스코드 웹훅을 통해 요약 브리핑을 전송합니다."""
    
    if not DISCORD_WEBHOOK_URL or DISCORD_WEBHOOK_URL == "복사한_디스코드_웹훅_URL_붙여넣기":
        print("⚠️ 디스코드 웹훅 URL이 설정되지 않아 알림을 생략합니다.")
        return

    # 디스코드에 보낼 메시지 본문 (마크다운 지원)
    content = f"## 📰 오늘의 일간 경제 리포트 도착!\n\n"
    content += f"**🎯 시장 키워드:** {keyword}\n"
    content += f"**💡 데스크 브리핑:** {overview}\n"
    content += f"**📊 매크로 지표:** {indicators}\n\n"
    content += f"📂 **파일 저장 완료:** `{filename}`"

    # payload 데이터 조립
    data = {
        "content": content,
        "username": "수석 경제 에디터", # 봇 이름
        "avatar_url": "https://cdn-icons-png.flaticon.com/512/2942/2942821.png" # 봇 프로필 이미지 (선택)
    }
    
    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=data)
        response.raise_for_status()
        print("🔔 디스코드 알림 전송 완료!")
    except Exception as e:
        print(f"❌ 디스코드 알림 전송 실패: {e}")
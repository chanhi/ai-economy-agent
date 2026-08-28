import requests
from config import DISCORD_WEBHOOK_URL

def send_discord_alert(keyword, overview, indicators, filepath):
    import os
    if not DISCORD_WEBHOOK_URL or DISCORD_WEBHOOK_URL == "your_discord_webhook_url_here":
        print("⚠️ 디스코드 웹훅 URL이 설정되지 않아 알림을 생략합니다.")
        return

    filename = os.path.basename(filepath)
    content = (
        f"## 📰 오늘의 일간 경제 리포트 도착!\n\n"
        f"**🎯 시장 키워드:** {keyword}\n"
        f"**💡 데스크 브리핑:** {overview}\n"
        f"**📊 매크로 지표:** {indicators}\n\n"
        f"📂 **파일 저장 완료:** `{filename}`"
    )

    data = {
        "content": content,
        "username": "수석 경제 에디터",
        "avatar_url": "https://cdn-icons-png.flaticon.com/512/2942/2942821.png"
    }
    
    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=data)
        response.raise_for_status()
        print("🔔 디스코드 알림 전송 완료!")
    except Exception as e:
        print(f"❌ 디스코드 알림 전송 실패: {e}")
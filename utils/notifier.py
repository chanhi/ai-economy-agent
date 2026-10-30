import os
import requests
from config import DISCORD_WEBHOOK_URL, ENABLE_DISCORD_ALERT, ECONOMY_TEST_MODE

def _can_send_webhook(force_on_error: bool = False) -> bool:
    if ECONOMY_TEST_MODE:
        return False
    if not DISCORD_WEBHOOK_URL or DISCORD_WEBHOOK_URL == "your_discord_webhook_url_here":
        return False
    return force_on_error or ENABLE_DISCORD_ALERT

def send_discord_alert(keyword: str, overview: str, indicators: str, filepath: str):
    if not _can_send_webhook(force_on_error=False):
        return

    filename = os.path.basename(filepath) if filepath else "unknown.md"
    content = (
        f"## 📰 오늘의 일간 경제 리포트 도착!\n\n"
        f"**🎯 시장 키워드:** {keyword}\n"
        f"**💡 데스크 브리핑:** {overview}\n"
        f"**📊 매크로 지표:** {indicators}\n\n"
        f"📂 **파일 저장 완료:** `{filename}`"
    )

    data = {
        "content": content[:1950],
        "username": "수석 경제 에디터",
        "avatar_url": "https://cdn-icons-png.flaticon.com/512/2942/2942821.png",
    }

    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=data, timeout=8)
        response.raise_for_status()
        print("🔔 디스코드 알림 전송 완료!")
    except Exception as e:
        print(f"❌ 디스코드 알림 전송 실패: {e}")

def send_error_alert(stage: str, error_message: str):
    """무인 운영 중 치명적 장애(대기열 고갈, API 전체 폴백 실패 등) 발생 시 경보를 전송합니다."""
    if not _can_send_webhook(force_on_error=True):
        return

    content = (
        f"## 🚨 [경보] Economy Agent 파이프라인 이상 감지\n"
        f"- **발생 단계:** `{stage}`\n"
        f"- **상세 내용:** {error_message[:1500]}"
    )
    try:
        requests.post(
            DISCORD_WEBHOOK_URL,
            json={"content": content, "username": "시스템 모니터"},
            timeout=8,
        )
    except Exception:
        pass

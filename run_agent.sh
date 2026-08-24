#!/bin/bash
# 실행될 때의 시간을 로그로 찍어줍니다.
echo "========================================"
echo "실행 시간: $(date +'%Y-%m-%d %H:%M:%S')"
echo "========================================"

cd /home/chan/economySummary

# 파이썬 실행
/home/chan/.local/bin/uv run main.py

# 깃허브 업로드 (옵시디언 동기화를 나중에 하신다고 했지만, 코드를 백업용으로 남겨둡니다)
# git add obsidian_notes/*.md
# git commit -m "Auto Update: $(date +'%Y-%m-%d %H:%M') 뉴스"
# git push origin main
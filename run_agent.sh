#!/bin/bash
echo "========================================"
echo "실행 시간: $(date +'%Y-%m-%d %H:%M:%S')"
echo "========================================"

# 1. 프로젝트 폴더로 이동하여 파이썬 파이프라인 실행
cd /home/chan/economySummary
/home/chan/.local/bin/uv run main.py

# 2. 노트 폴더로 이동하여 Private 저장소로 자동 Push
cd /home/chan/economySummary/obsidian_notes
git add .
# 오늘 날짜를 커밋 메시지로 남김
git commit -m "Auto update: $(date +'%Y-%m-%d %H:%M:%S')"
git push origin main

echo "✅ 일간 리포트 생성 및 Private 저장소 백업 완료!"
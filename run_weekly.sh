#!/bin/bash
echo "========================================"
echo "주간 결산 실행 시간: $(date +'%Y-%m-%d %H:%M:%S')"
echo "========================================"

cd /home/chan/economySummary
/home/chan/.local/bin/uv run weekly_summary.py

# 노트 폴더 백업 및 Push
cd /home/chan/economySummary/obsidian_notes
git add .
git commit -m "Auto Weekly Update: $(date +'%Y-%m-%d %H:%M:%S')"
git push origin main

echo "✅ 주간 리포트 생성 및 백업 완료!"
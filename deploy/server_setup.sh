#!/usr/bin/env bash
# 서버(EC2)에서 실행: 파이썬 가상환경 준비 → 패키지 설치 → systemd 서비스 등록/재시작 → 상태 확인
# GitHub Actions 가 배포할 때 자동으로 부릅니다. 직접 실행해도 됩니다: bash deploy/server_setup.sh
set -euo pipefail

APP_DIR="${APP_DIR:-/home/ubuntu/AI-assistant-PR}"
SERVICE=uos-assistant
cd "$APP_DIR"

if [ ! -f .env ]; then
  echo "오류: $APP_DIR/.env 가 없습니다." >&2
  exit 1
fi
chmod 600 .env
mkdir -p /home/ubuntu/uos-assistant-data

echo "== 파이썬 패키지 설치"
[ -x .venv/bin/python ] || python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt

echo "== 서비스 등록 및 재시작"
sudo cp deploy/uos-assistant.service /etc/systemd/system/$SERVICE.service
sudo systemctl daemon-reload
sudo systemctl enable -q $SERVICE
started="$(date '+%Y-%m-%d %H:%M:%S')"
sudo systemctl restart $SERVICE

echo "== 상태 확인"
ok=0
for _ in $(seq 1 20); do
  if curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then ok=1; break; fi
  sleep 2
done
sleep 8 # 디스코드 로그인 결과가 로그에 찍힐 시간
logs="$(sudo journalctl -u $SERVICE --since "$started" --no-pager || true)"

if [ "$ok" != 1 ] || echo "$logs" | grep -q "Discord bot stopped"; then
  echo "$logs" | tail -n 60
  echo "배포 실패: 위 로그를 확인하세요. (토큰이 틀리면 LoginFailure 가 보입니다)" >&2
  exit 1
fi

echo "$logs" | tail -n 15
echo "배포 완료: 봇이 실행 중입니다."

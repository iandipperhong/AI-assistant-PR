# UOS 생활 비서 🤖

서울시립대학교 학생용 대학생활 비서 텔레그램 봇입니다.
시간표·과제·시험을 등록하면 마감 전에 알려주고, "내일 과제 뭐 있어?"처럼 말로 물어볼 수 있습니다.

## 로드맵

- **1단계 (지금)**: 시간표/과제/시험 등록, 마감 알림, 자연어 질문 · 등록
- **2단계**: 학식·학사일정 자동 수집 → 조사 결과 [docs/uos-sources.md](docs/uos-sources.md), 파서 초안 `app/campus/`
- **3단계**: 시험 준비 도우미 (`Exam.scope` 칸 준비됨)

## 구조

```
app/
  main.py          FastAPI + 텔레그램 봇(롱폴링) + 알림 작업 실행
  config.py        .env 설정
  db.py, models.py SQLite + SQLAlchemy (시간표, 과제, 시험, 보낸 알림)
  repository.py    DB 읽기/쓰기
  parsing.py       "12/03 23:59", "월 09:00-10:15" 같은 입력 파싱
  assistant.py     자연어 처리 (LLM이 JSON으로 행동을 고르고, DB 저장은 코드가 검증 후 처리)
  reminders.py     과제 24시간/3시간 전, 시험 3일/1일 전 알림 (중복 방지)
  bot/             텔레그램 명령어 핸들러와 메시지 포맷
  llm/             LLM 추상화: gemini(기본) · claude · ollama
  campus/          (2단계) 학식/학사일정 파서 초안
deploy/            systemd 서비스 파일
tests/             pytest
```

### LLM 바꾸기

`.env` 의 `LLM_PROVIDER` 만 바꾸면 됩니다: `gemini`(기본, 무료 티어) · `claude` · `ollama`(로컬).
다른 모델을 붙이려면 `app/llm/base.py` 의 `LLMProvider.generate()` 하나만 구현하세요.

## 봇 명령어

| 명령 | 예시 |
|---|---|
| 수업 추가 | `/class_add 월 09:00-10:15 자료구조 @21세기관301` |
| 과제 추가 | `/hw_add 12/03 23:59 자료구조 과제3 보고서` (시간 생략 시 23:59, 첫 단어=과목) |
| 시험 추가 | `/exam_add 12/10 10:00 자료구조 기말고사 @정보기술관` |
| 조회 | `/today` `/tomorrow` `/week` `/hw` `/exams` `/timetable` |
| 관리 | `/done 3` · `/del hw 3` · `/del exam 2` · `/del class 1` |
| 그냥 말하기 | "내일 과제 뭐 있어?", "금요일까지 운영체제 과제2 등록해줘" |

날짜는 `12/03`, `2026-12-03`, `오늘`, `내일`, `모레` 를 쓸 수 있습니다.

## 설치 (AWS 서버)

1. **텔레그램 봇 만들기**: 텔레그램에서 `@BotFather` → `/newbot` → 토큰 복사
2. **Gemini API 키**: https://aistudio.google.com/apikey 에서 발급 (무료)
3. 서버에서:
   ```bash
   git clone https://github.com/iandipperhong/AI-assistant-PR.git
   cd AI-assistant-PR
   python3 -m venv .venv && . .venv/bin/activate
   pip install -r requirements.txt
   cp .env.example .env   # 토큰, API 키 입력
   uvicorn app.main:api --host 127.0.0.1 --port 8000
   ```
4. 봇에게 `/start` → 알려주는 chat id 를 `.env` 의 `ALLOWED_CHAT_IDS` 에 넣고 재시작 (나만 쓰도록 잠금)
5. 상시 실행: `deploy/uos-assistant.service` 를 경로에 맞게 고쳐서 systemd 에 등록

롱폴링 방식이라 서버에 포트를 열거나 도메인이 없어도 됩니다. `/health` 는 127.0.0.1 에서만 열어 두었습니다.

## 개발

```bash
pip install -r requirements-dev.txt
pytest
```

## 과제 자동 가져오기는?

지금은 수동 입력이 기본입니다. uClass(Moodle 기반)의 캘린더 내보내기(iCal) 주소를 쓰면 비밀번호 없이 자동으로 가져올 수 있을 것 같아, 2단계에서 확인하려 합니다. 자세한 내용은 [docs/uos-sources.md](docs/uos-sources.md).

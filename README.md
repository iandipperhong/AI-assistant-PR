# UOS 생활 비서 🤖

서울시립대학교 학생용 대학생활 비서 **디스코드 봇**입니다.
시간표·과제·시험을 등록하면 마감 전에 알려주고, "내일 과제 뭐 있어?"처럼 말로 물어볼 수 있습니다.

## 로드맵

- **1단계 (지금)**: 시간표/과제/시험 등록, 마감 알림, 자연어 질문 · 등록
- **2단계**: 학식·학사일정 자동 수집 → 조사 결과 [docs/uos-sources.md](docs/uos-sources.md), 파서 초안 `app/campus/`
- **3단계**: 시험 준비 도우미 (`Exam.scope` 칸 준비됨)

## 구조

```
app/
  main.py          FastAPI 안에서 디스코드 봇 실행
  config.py        .env 설정
  db.py, models.py SQLite + SQLAlchemy (시간표, 과제, 시험, 보낸 알림)
  repository.py    DB 읽기/쓰기
  parsing.py       "12/03 23:59", "월 09:00-10:15" 같은 입력 파싱
  assistant.py     자연어 처리 (LLM이 JSON으로 행동을 고르고, DB 저장은 코드가 검증 후 처리)
  reminders.py     과제 24시간/3시간 전, 시험 3일/1일 전 알림 계산 (중복 방지)
  bot/client.py    디스코드: 슬래시 명령어 등록, DM/멘션 대화, 5분마다 DM 알림
  bot/commands.py  명령어 동작 (디스코드와 분리된 순수 함수)
  bot/formatting.py 목록 → 메시지 문자열
  llm/             LLM 추상화: gemini(기본) · claude · ollama
  campus/          (2단계) 학식/학사일정 파서 초안
deploy/            systemd 서비스 파일, 서버 설치 스크립트
.github/workflows/ 자동 배포 (GitHub Actions)
tests/             pytest
```

### LLM 바꾸기

`.env` 의 `LLM_PROVIDER` 만 바꾸면 됩니다: `gemini`(기본, 무료 티어) · `claude` · `ollama`(로컬).
다른 모델을 붙이려면 `app/llm/base.py` 의 `LLMProvider.generate()` 하나만 구현하세요.

## 봇 명령어 (슬래시 명령어)

| 명령 | 입력 칸 |
|---|---|
| `/class_add` | 요일(선택), 시간 `09:00-10:15`, 과목, 장소(선택) |
| `/hw_add` | 날짜, 과목, 제목, 시간(선택, 기본 23:59) |
| `/exam_add` | 날짜, 시간, 과목, 시험이름(선택), 장소(선택) |
| 조회 | `/today` `/tomorrow` `/week` `/hw` `/exams` `/timetable` |
| 관리 | `/done` 과제 완료 · `/del` 삭제 |
| 기타 | `/help` · `/whoami` (내 사용자 ID 확인) |

날짜는 `12/03`, `2026-12-03`, `오늘`, `내일`, `모레` 를 쓸 수 있습니다.
서버 채널에서 쓴 명령의 답은 **나에게만 보이게** 옵니다.

**말로 하기**: 봇에게 DM을 보내거나, 서버 채널에서 `@봇이름` 으로 멘션하세요.
"내일 과제 뭐 있어?", "금요일까지 운영체제 과제2 등록해줘"

**알림**은 DM으로 옵니다.

## 설치

### 1. 디스코드 봇 만들기
1. https://discord.com/developers/applications → **New Application**
2. **Bot** 탭 → **Reset Token** → 토큰 복사 (`DISCORD_BOT_TOKEN`)
   - 특권 인텐트(Message Content 등)는 켤 필요 없습니다. DM과 멘션 내용은 기본으로 읽힙니다.
3. **Installation** 탭 → Installation Contexts 에서 **User Install** 과 **Guild Install** 둘 다 체크
   - Guild Install 의 scopes: `bot`, `applications.commands` / 권한: `Send Messages`, `Read Message History`
   - User Install 의 scopes: `applications.commands`
4. Install Link 로 내 서버에 초대 (또는 내 계정에 설치)
   - 봇이 DM 알림을 보내려면 **봇과 같은 서버에 있거나, 봇에게 먼저 DM을 한 번 보내 두는 것**이 안전합니다.
5. (선택) 내 서버 ID를 `DISCORD_GUILD_ID` 에 넣으면 슬래시 명령어가 바로 뜹니다. 안 넣으면 전역 등록이라 처음 뜨기까지 최대 1시간 걸릴 수 있어요.
   - 서버 ID: 디스코드 설정 → 고급 → 개발자 모드 켜기 → 서버 우클릭 → ID 복사

### 2. Gemini API 키
https://aistudio.google.com/apikey 에서 발급 (무료)

### 3. 자동 배포 (GitHub Actions → AWS 서버)

`main` 브랜치에 코드가 올라가면 GitHub 가 알아서 테스트 → 서버로 복사 → 설치 → 봇 재시작까지 합니다.
서버에 직접 들어가서 할 일은 없습니다. (git, python 가상환경 등도 처음 배포 때 자동 설치)

#### 3-1. AWS 보안 그룹에서 SSH 열기
GitHub 의 배포 컴퓨터는 매번 IP 가 바뀌어서, "내 IP" 로만 열어 두면 접속하지 못합니다.

1. AWS 콘솔 → **EC2** → **인스턴스** → 내 서버 클릭 → 아래 **보안** 탭 → 보안 그룹 이름 클릭
2. **인바운드 규칙 편집** → SSH(22) 규칙의 소스를 **0.0.0.0/0 (Anywhere-IPv4)** 로 → 저장

> 괜찮을까요? EC2(Ubuntu)는 비밀번호 로그인이 꺼져 있고 **.pem 키가 있어야만** 들어갈 수 있어서, 키만 잘 지키면 안전합니다.

#### 3-2. GitHub 에 Secrets 등록
토큰과 키는 코드에 넣지 않고 GitHub 의 금고(Secrets)에 넣습니다. 등록한 값은 다시 볼 수 없고 로그에도 `***` 로 가려집니다.
**채팅이나 코드에 붙여 넣지 마세요.**

1. GitHub 저장소 페이지 → 위쪽 **Settings** 탭
2. 왼쪽 메뉴 **Secrets and variables** → **Actions**
3. **New repository secret** 버튼 → Name 과 Secret 을 넣고 **Add secret**. 아래 표대로 하나씩 반복

| Name (그대로 입력) | 넣을 값 | 어디서 찾나요 |
|---|---|---|
| `EC2_HOST` | 서버 IP (예: `3.35.123.45`) | AWS 콘솔 → EC2 → 인스턴스 → **퍼블릭 IPv4 주소** |
| `EC2_SSH_KEY` | `.pem` 파일 내용 **전체** | 서버 만들 때 받은 `.pem` 파일을 **메모장으로 열어** `-----BEGIN` 줄부터 `-----END ... KEY-----` 줄까지 전부 복사 |
| `DISCORD_BOT_TOKEN` | 디스코드 봇 토큰 | 위 1번 단계 |
| `GEMINI_API_KEY` | Gemini API 키 | 위 2번 단계 |
| `ALLOWED_USER_IDS` | (선택) 내 디스코드 사용자 ID | 아래 4번 단계. 처음엔 비워도 배포됩니다 |
| `DISCORD_GUILD_ID` | (선택) 내 디스코드 서버 ID | 위 1번 단계의 5 |

> 서버를 **중지했다가 다시 켜면 퍼블릭 IP 가 바뀝니다.** 그러면 `EC2_HOST` 를 새 IP 로 다시 등록하세요. (바뀌지 않게 하려면 AWS 의 "탄력적 IP" 를 붙이면 됩니다)

#### 3-3. 배포하기
- PR 을 `main` 에 병합(Merge)하면 자동으로 시작합니다.
- 코드 변경 없이 다시 배포하려면: 저장소 → **Actions** 탭 → 왼쪽 **서버에 자동 배포** → **Run workflow**
- 진행 상황도 **Actions** 탭에서 봅니다. 초록 체크면 성공, 빨간 X 면 눌러서 어느 단계에서 실패했는지 확인하세요.
  - "Secrets 확인" 실패 → 빠진 Secret 이름이 나옵니다
  - "SSH 접속 준비" 실패 → 보안 그룹(3-1), `EC2_HOST` IP, `EC2_SSH_KEY` 내용 확인
  - "설치하고 봇 재시작" 실패 → 아래에 봇 로그가 나옵니다 (토큰이 틀리면 `LoginFailure`)

Secret 값을 바꾼 뒤에는 **Run workflow** 로 한 번 다시 배포해야 서버에 반영됩니다.

### 4. 나만 쓰도록 잠그기
디스코드에서 `/whoami` → 나온 ID 를 GitHub Secret `ALLOWED_USER_IDS` 에 등록 → **Run workflow** 로 다시 배포.

### 5. 서버에서 상태 보기 (필요할 때만)
```bash
sudo systemctl status uos-assistant     # 실행 중인지
sudo journalctl -u uos-assistant -f     # 실시간 로그 (Ctrl+C 로 나가기)
```
봇은 디스코드 쪽으로 연결을 여는 방식이라 서버에 22번 말고 다른 포트를 열 필요가 없습니다. `/health` 는 서버 안(127.0.0.1)에서만 열려 있습니다.
데이터(SQLite DB)는 `/home/ubuntu/uos-assistant-data/` 에 있어 다시 배포해도 지워지지 않습니다.

<details>
<summary>자동 배포 없이 직접 설치하려면</summary>

```bash
sudo apt-get update && sudo apt-get install -y git python3-venv
git clone https://github.com/iandipperhong/AI-assistant-PR.git
cd AI-assistant-PR
cp .env.example .env   # 토큰, API 키 입력
bash deploy/server_setup.sh
```
</details>

## 개발

```bash
pip install -r requirements-dev.txt
pytest
```

## 과제 자동 가져오기는?

지금은 수동 입력(`/hw_add` 나 말로 등록)이 기본입니다. uClass(Moodle 기반)의 캘린더 내보내기(iCal) 주소를 쓰면 비밀번호 없이 자동으로 가져올 수 있을 것 같아, 2단계에서 확인하려 합니다. 자세한 내용은 [docs/uos-sources.md](docs/uos-sources.md).

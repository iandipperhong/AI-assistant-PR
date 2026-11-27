# 서울시립대 데이터 출처 조사 (2026-11-27)

브라우저로 실제 페이지를 열어 구조를 확인했습니다. **공식 API(JSON/iCal)는 찾지 못했고**, 둘 다 서버에서 그린 HTML이라 파싱으로 가져와야 합니다.

## 학식 (식단표)

- 페이지: https://www.uos.ac.kr/food/placeList.do
- 식당 선택: 쿼리 `rstcde`
  | 코드 | 식당 |
  |---|---|
  | 020 (기본) | 학생회관 1층 |
  | 010 | 100주년기념관 이룸라운지 |
  | 030 | 양식당 |
  | 040 | 자연과학관 |
- 날짜 선택: **POST** 폼 값 `search_date=YYYYMMDD`. GET 쿼리(`?search_date=`)로 보내면 빈 응답(약 500바이트)이 와서 안 됩니다.
- 구조: `div.listType02` 안 첫 번째 `table` 의 `td` 3개가 조식/중식/석식. 각 칸에 코너, 시간, 가격, 메뉴, 원산지, 칼로리가 `<br>` 로 나열됩니다.
- "주간별보기" 표도 같은 페이지에 있어서, 한 번 요청으로 한 주를 받을 수도 있습니다 (2단계에서 확인).
- 파서 초안: `app/campus/uos_meal.py`

## 학사일정

- 페이지: https://www.uos.ac.kr/korCalendarYear/list.do?list_id=CA1 (학부)
- 대학원은 별도: https://graduate.uos.ac.kr/graduateNew/korCalendarYear2/list.do?list_id=30001C4
- 연도 선택: **POST** `list_id=CA1&year_code=YYYY`
- 구조: 월마다 `th.date01`("2026년 01월"), 각 행에 `td.date02`("[12-22 ~ 01-19]")와 `td.title01`(일정 이름, 한/영 병기).
  1월 칸에 전년도 12월에 시작하는 일정이 섞여 있어서 연도 보정이 필요합니다 (파서에 반영).
- 1년에 몇 번만 바뀌므로 하루 한 번 가져와 DB에 저장하면 충분합니다.
- 파서 초안: `app/campus/uos_calendar.py`

## 조경학과 공지

- 페이지: https://lauos.or.kr/notice (워드프레스 KBoard)
- 목록 `table tbody tr`: 링크의 `uid=` 가 글 번호, 제목 `.kboard-default-cut-strings`, 날짜 `td.kboard-list-date`
- 파서: `app/campus/lauos_notice.py`. 30분마다 확인해서 처음 보는 uid 만 #알림 채널로 보냅니다.

## SSO 건너뛰기 (2026-11-27 확인)

`www.uos.ac.kr` 페이지 주소에 `identified=anonymous` 를 붙이면 SSO 자바스크립트 리다이렉트 없이, 쿠키 없이 바로 열립니다.
학식(`/food/placeList.do?identified=anonymous&rstcde=010`, POST `search_date`)과 학사일정(POST `list_id=CA1&year_code=YYYY`) 모두 확인했습니다.

## 교과과정 · 졸업학점 (2026-11-28 확인)

- 페이지: https://www.uos.ac.kr/kor/html/uaInfo/major/curriculum/curriculum2026.do (학과별 hwp 다운로드)
- 다운로드: POST `/common/dir/FileDown.do` (`file_path=/data/26_cu/`, `file_upNm`, `file_orgNm` = 파일 이름)
- 조경학과: `7. 조경학과.hwp`, 졸업학점: `2026 졸업최저이수학점.hwp` → `app/campus/landscape_curriculum.py` 에 옮겨 둠
- 공통 졸업요건: https://www.uos.ac.kr/kor/html/uaInfo/graduate/terms/terms.do

## 주의할 점

- `www.uos.ac.kr` 은 처음 접속하면 SSO 페이지(`/exsignon/sso/sso_index.jsp`)를 거쳐 `identified=anonymous` 로 돌아옵니다.
  로그인은 필요 없지만 쿠키를 유지해야 하고, 리다이렉트가 자바스크립트로 이뤄지는지는 AWS 서버에서 직접 요청해 보고 확인해야 합니다.
- 해외 IP나 일부 클라우드에서는 학교 사이트가 막힐 수 있습니다 (이 작업 환경에서도 직접 접속은 막혀 있었음). AWS 서울 리전이면 문제없을 가능성이 큽니다.
- 요청은 하루 몇 번 수준으로 제한하고 결과를 캐시하세요.

## 과제 자동 가져오기 (미정)

- 온라인강의실 **uClass**: https://uclass.uos.ac.kr (로그인 페이지가 `/login/index.php` 라서 **Moodle** 기반으로 보입니다).
- 선택지:
  1. **수동 입력 (현재 기본값)**: `/hw_add` 슬래시 명령어 또는 "금요일까지 OS 과제 등록해줘" 같은 말로 등록.
  2. **Moodle 캘린더 내보내기(iCal URL)**: Moodle 은 보통 "캘린더 → 내보내기"에서 개인 토큰이 들어간 .ics 주소를 줍니다.
     uClass 에서 이 메뉴가 켜져 있다면 비밀번호를 저장하지 않고도 과제 마감을 자동으로 가져올 수 있어 가장 안전한 방법입니다. 로그인 후 확인이 필요합니다.
  3. 학교 계정으로 로그인해 스크래핑: 비밀번호를 서버에 저장해야 하고 학교 정책 문제도 있어 비추천.
- `Assignment` 모델에 `source`, `external_id` 칸을 미리 만들어 두어서, 나중에 2번을 붙여도 중복 없이 합칠 수 있습니다.

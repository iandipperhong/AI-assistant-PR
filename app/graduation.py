"""졸업요건 계산: 내가 입력한 이수 과목 → 학점 합계, 남은 학점, 안 들은 전공 과목."""
from __future__ import annotations

from collections import defaultdict

from app.campus import landscape_curriculum as cur
from app.models import CompletedCourse


def totals(courses: list[CompletedCourse]) -> dict[str, int]:
    t: dict[str, int] = defaultdict(int)
    for c in courses:
        t[c.category] += c.credits
        if c.category.startswith("전공"):
            t["전공"] += c.credits
        if c.category.startswith("교양"):
            t["교양"] += c.credits
    # 졸업학점에는 교양을 48학점까지만 인정
    t["총"] = sum(c.credits for c in courses) - max(t["교양"] - cur.LIBERAL_ARTS_CAP, 0)
    return dict(t)


def summary(courses: list[CompletedCourse], rules: dict[str, int | None] | None = None,
            required: list[str] | None = None, prereq: dict[str, list[str]] | None = None) -> str:
    rules = cur.GRAD_RULES if rules is None else rules
    required = cur.REQUIRED_COURSES if required is None else required
    prereq = cur.PREREQUISITES if prereq is None else prereq
    t = totals(courses)
    taken = {cur.normalize(c.name) for c in courses}

    lines = ["🎓 **졸업요건** (조경학과, 2026 입학생 기준)", "", "**학점**"]
    for key, need in rules.items():
        have = t.get(key, 0)
        if need is None:
            lines.append(f"  {key}: {have}학점 이수 · 기준 요람 확인 필요")
        else:
            left = max(need - have, 0)
            mark = "✅" if left == 0 else f"{left}학점 남음"
            lines.append(f"  {key}: {have} / {need}학점 · {mark}")
    if t.get("교양", 0) > cur.LIBERAL_ARTS_CAP:
        lines.append(f"  ※ 교양은 {cur.LIBERAL_ARTS_CAP}학점까지만 총 학점에 들어가요")
    for key in ("전공선택", "교양선택", "일반선택"):
        if key not in rules and t.get(key):
            lines.append(f"  {key}: {t[key]}학점 이수")

    if required:
        missing = [c for c in required if cur.normalize(c) not in taken]
        lines += ["", "**전공필수 미이수**", "  " + (", ".join(missing) if missing else "없음 ✅")]
    else:
        lines += ["", "**전공필수**: 요람에서 지정 과목을 확인하면 여기에 남은 과목이 떠요."]

    if prereq:
        warn = []
        for course, needs in prereq.items():
            if cur.normalize(course) in taken:
                continue
            lacking = [n for n in needs if cur.normalize(n) not in taken]
            if lacking:
                warn.append(f"  {course} ← 먼저: {', '.join(lacking)}")
        if warn:
            lines += ["", "**선수과목 아직 안 들음**"] + warn

    lines += ["", "**안 들은 전공 과목** (2026 교과과정)"]
    for year, names in sorted(cur.CURRICULUM.items()):
        left = [n for n in names if cur.normalize(n) not in taken]
        lines.append(f"  {year}학년: " + (", ".join(left) if left else "모두 이수 ✅"))

    lines += ["", "**그 밖의 졸업요건** (직접 확인)"] + [f"  ☐ {r}" for r in cur.COMMON_REQUIREMENTS]
    lines += ["", f"입력한 과목 {len(courses)}개 · 과목 추가/삭제는 아래 버튼"]
    return "\n".join(lines)


def course_list_text(courses: list[CompletedCourse]) -> str:
    if not courses:
        return "아직 입력한 과목이 없어요."
    return "\n".join(f"  #{c.id} {c.name} ({c.category}, {c.credits}학점)" for c in courses)

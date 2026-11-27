import os
import sys
import tempfile
from pathlib import Path

# app 을 import 하기 전에 테스트용 DB/설정을 지정
_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["ALLOWED_USER_IDS"] = ""
os.environ["ASSIGNMENT_REMIND_HOURS"] = "24,3"
os.environ["EXAM_REMIND_HOURS"] = "72,24"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app.db import Base, SessionLocal, engine, init_db  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    init_db()
    yield


@pytest.fixture
def session():
    s = SessionLocal()
    yield s
    s.commit()
    s.close()

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FIX = Path(__file__).parent / "fixtures"
API = FIX / "api"
KNOW = FIX / "knowledge"
ET = ZoneInfo("America/New_York")
NOW = datetime(2026, 10, 14, 5, 0, tzinfo=ET)


@pytest.fixture
def now():
    return NOW


@pytest.fixture
def http():
    from engine.http import Http, RunLog
    return Http(RunLog(), offline_dir=str(API))


@pytest.fixture
def kn():
    from engine.knowledge import Knowledge
    return Knowledge(KNOW)

import pytest
from pathlib import Path
from datetime import datetime


@pytest.fixture(scope='session')
def session_log_dir() -> Path:
    _session_log_dir = Path('logs' , f"{datetime.now().strftime('%Y_%m_%d-%H_%M_%S')}")
    _session_log_dir.mkdir(parents=True, exist_ok=True)

    return _session_log_dir


@pytest.fixture(scope='function')
def log_dir(request: pytest.FixtureRequest, session_log_dir: Path):

    _log_dir = session_log_dir / request.node.name
    _log_dir.mkdir(parents=True, exist_ok=True)

    return _log_dir

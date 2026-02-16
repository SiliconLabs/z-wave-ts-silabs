import pytest
import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path if z_wave_ts_silabs is not installed
# This allows importing fixtures when running pytest from examples directory
_parent_dir = Path(__file__).parent.parent
if str(_parent_dir) not in sys.path:
    sys.path.insert(0, str(_parent_dir))

# Import all fixtures from z_wave_ts_silabs.fixtures
# Pytest will automatically discover and register these fixtures
# The fixtures module uses pytest hooks which are only registered once
from z_wave_ts_silabs.fixtures import *


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

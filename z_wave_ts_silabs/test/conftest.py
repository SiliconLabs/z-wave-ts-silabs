import pytest
from pathlib import Path

# z_wave_ts_silabs needs this fixture to exists in order to work properly
@pytest.fixture(scope='session')
def log_dir():
    return Path.cwd()

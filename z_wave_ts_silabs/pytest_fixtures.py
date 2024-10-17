import os
import pytest

from z_wave_ts_silabs import config
from z_wave_ts_silabs import Cluster, DevWpk, BackgroundProcess

logger = config.LOGGER.getChild(__name__)

@pytest.fixture(scope="function", autouse=True)
def cleanup_background_processes():
    BackgroundProcess.stop_all()
    yield
    BackgroundProcess.stop_all()

@pytest.fixture(scope="function", autouse=True)
def setup_logs(request):
    test_name = request.node.originalname
    config.LOGDIR_CURRENT_TEST = f"{config.LOGDIR}/{test_name}"
    # the mkdir below should never raise an error since function names should be unique in a test file 
    # TODO: check if that's true in the future
    os.mkdir(config.LOGDIR_CURRENT_TEST)
    logger.debug(f'current test log directory: {config.LOGDIR_CURRENT_TEST}')

@pytest.fixture(scope="function")
def get_wpks_from_cluster():
    def _func(cluster_name: str):
        cluster = Cluster.from_json(config.CONFIG["clusters"], cluster_name)
        dev_wpks = []
        for wpk in cluster.wpks:
            dev_wpks.append(DevWpk(wpk.serial, f"jlink{wpk.serial}.silabs.com"))
        return dev_wpks
    return _func

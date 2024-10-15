import os
import pytest
from typing import List
from pathlib import Path

from z_wave_ts_silabs import DevWpk, DevCluster, BackgroundProcess, ctxt, DevTimeServer
from z_wave_ts_silabs.device_factory import DeviceFactory

logger = ctxt.session_logger.getChild(__name__)


def pytest_addoption(parser: pytest.Parser):
    parser.addoption(
        '--hw-cluster', required=True, type=str, help='Cluster to run the test session on', choices=ctxt.clusters
    )


@pytest.fixture(scope='session', autouse=True)
def hw_cluster_name(pytestconfig: pytest.Config) -> str:
    yield pytestconfig.getoption('hw_cluster')


@pytest.fixture(scope="session", autouse=True)
def hw_cluster(hw_cluster_name: str) -> DevCluster:
    cluster = ctxt.clusters[hw_cluster_name]
    dev_wpks: List[DevWpk] = []
    # This object is used to synchronize the timestamps of all WPK in the cluster
    time_server: DevTimeServer = DevTimeServer()

    for wpk in cluster.wpks:
        dev_wpks.append(
            DevWpk(wpk.serial, f"jlink{wpk.serial}.silabs.com", time_server=time_server)
        )
    yield DevCluster(hw_cluster_name, dev_wpks)


@pytest.fixture(scope='function')
def device_factory(hw_cluster: DevCluster) -> DeviceFactory:
    factory = DeviceFactory(hw_cluster)
    yield factory
    factory.finalize()



@pytest.fixture(scope="function", autouse=True)
def hw_cluster_free_all_wpk(hw_cluster: DevCluster):
    hw_cluster.free_all_wpk()
    yield
    hw_cluster.free_all_wpk()


@pytest.fixture(scope="function", autouse=True)
def cleanup_background_processes():
    BackgroundProcess.stop_all()
    yield
    BackgroundProcess.stop_all()


@pytest.fixture(scope="function", autouse=True)
def setup_logs(request):
    # request.node.originalname contains the test name:
    ctxt.session_logdir_current_test = f"{ctxt.session_logdir}/{request.node.originalname}"
    # the mkdir below should never raise an error since function names should be unique in a test file
    os.mkdir(ctxt.session_logdir_current_test)
    logger.debug(f'current test log directory: {ctxt.session_logdir_current_test}')

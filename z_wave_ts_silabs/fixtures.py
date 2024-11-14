import os
import pytest
import logging

from z_wave_ts_silabs import DevWpk, DevCluster, BackgroundProcess, DevTimeServer
from z_wave_ts_silabs.device_factory import DeviceFactory
from z_wave_ts_silabs.session_context import SessionContext


_logger = logging.getLogger(__name__)
_CONFIG_FILE_PATH = f'{os.getcwd()}/config.json'


def pytest_addoption(parser: pytest.Parser):
    ctxt = SessionContext.from_json(_CONFIG_FILE_PATH)
    parser.addoption(
        '--hw-cluster', required=True, type=str, help='Cluster to run the test session on', choices=ctxt.clusters
    )


@pytest.fixture(scope='session', autouse=True)
def hw_cluster_name(pytestconfig: pytest.Config) -> str:
    yield pytestconfig.getoption('hw_cluster')


@pytest.fixture(scope="session", autouse=True)
def session_ctxt() -> SessionContext:
    yield SessionContext.from_json(_CONFIG_FILE_PATH)


@pytest.fixture(scope="session", autouse=True)
def hw_cluster(session_ctxt: SessionContext, hw_cluster_name: str) -> DevCluster:
    wpk_list = session_ctxt.clusters[hw_cluster_name]
    dev_wpks: list[DevWpk] = []
    # This object is used to synchronize the timestamps of all WPK in the cluster
    time_server: DevTimeServer = DevTimeServer()

    for wpk in wpk_list:
        dev_wpks.append(
            DevWpk(session_ctxt, wpk.serial, f"jlink{wpk.serial}.silabs.com", time_server=time_server)
        )
    yield DevCluster(hw_cluster_name, dev_wpks)


@pytest.fixture(scope='function')
def device_factory(session_ctxt: SessionContext, hw_cluster: DevCluster) -> DeviceFactory:
    factory = DeviceFactory(session_ctxt, hw_cluster)
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
def setup_logs(session_ctxt: SessionContext, request: pytest.FixtureRequest):
    # request.node.originalname contains the test name:
    session_ctxt.current_test_logdir = f"{session_ctxt.logdir}/{request.node.originalname}"
    # the mkdir below should never raise an error since function names should be unique in a test file
    os.mkdir(session_ctxt.current_test_logdir)
    _logger.debug(f'current test log directory: {session_ctxt.current_test_logdir}')

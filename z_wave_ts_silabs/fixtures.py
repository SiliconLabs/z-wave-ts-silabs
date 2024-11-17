import os
import json
import pytest
import logging
from pathlib import Path

from z_wave_ts_silabs import DevWpk, DevCluster, BackgroundProcess, DevTimeServer
from z_wave_ts_silabs.device_factory import DeviceFactory
from z_wave_ts_silabs.session_context import SessionContext, Clusters, Wpk


_logger = logging.getLogger(__name__)


def pytest_addoption(parser: pytest.Parser):
    parser.addoption(
        '--hw-cluster', type=str, help='Cluster to run the test session on'
    )
    parser.addoption(
        '--hw-config', type=str, help='Path to configuration JSON file', default='config.json'
    )


@pytest.fixture(scope='session')
def hw_cluster_name(pytestconfig: pytest.Config) -> str:
    yield pytestconfig.getoption('hw_cluster')


@pytest.fixture(scope='session')
def hw_config_path(pytestconfig: pytest.Config) -> Path:
    yield Path(pytestconfig.getoption('hw_config'))


@pytest.fixture(scope="session")
def session_ctxt(hw_config_path: Path) -> SessionContext:
    if hw_config_path.exists():
        _session_ctxt = SessionContext.from_json(hw_config_path)
    else:
        _session_ctxt = SessionContext() # session context with default values.
    yield _session_ctxt


@pytest.fixture(scope='session')
def hw_clusters(session_ctxt: SessionContext) -> Clusters:
    # loads the cluster dict from the JSON file.
    _hw_clusters: Clusters = {}

    try:
        with open(session_ctxt.clusters_json, 'r') as f:
            clusters_dict = json.load(f)

            for name, wpk_list in clusters_dict.items():
                _hw_clusters[name] = Wpk.from_json_list(wpk_list)
    except FileNotFoundError:
        # this fixture will return an empty Clusters object if the file is not found,
        # this is on purpose to be able to interface with z_wave_ts from the z-wave-test-system without breaking it.
        pass

    yield _hw_clusters


@pytest.fixture(scope="session")
def hw_cluster(session_ctxt: SessionContext, hw_clusters: Clusters, hw_cluster_name: str) -> DevCluster:
    dev_wpks: list[DevWpk] = []
    # This object is used to synchronize the timestamps of all WPK in the cluster
    time_server: DevTimeServer = DevTimeServer()

    if hw_clusters.get(hw_cluster_name) is not None:
        for wpk in hw_clusters[hw_cluster_name]:
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
    # request.node.name contains the test name with the parameters if any:
    session_ctxt.current_test_logdir = f"{session_ctxt.logdir}/{request.node.name}"
    # the mkdir below should never raise an error since function names should be unique in a test file
    os.mkdir(session_ctxt.current_test_logdir)
    _logger.debug(f'current test log directory: {session_ctxt.current_test_logdir}')

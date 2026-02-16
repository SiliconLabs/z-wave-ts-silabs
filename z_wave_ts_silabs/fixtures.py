import os
import json
import pytest
import socket
import logging
from pathlib import Path

from z_wave_ts_silabs import DevWpk, DevCluster, BackgroundProcess, DevTimeServer
from z_wave_ts_silabs.device_factory import DeviceFactory
from z_wave_ts_silabs.session_context import SessionContext, Clusters, Wpk


_logger = logging.getLogger(__name__)


def pytest_addoption(parser: pytest.Parser):
    """Add command line options for hardware testing.
    This function is idempotent - it safely handles duplicate registration attempts.
    """
    # Use try/except to handle cases where options are already registered
    # This can happen when the module is loaded both as a plugin and via import
    try:
        parser.addoption(
            '--hw-cluster', type=str, default=None, help='Cluster to run the test session on'
        )
    except ValueError:
        # Option already registered, ignore
        pass
    
    try:
        parser.addoption(
            '--hw-config', type=str, help='Path to configuration JSON file', default='config.json'
        )
    except ValueError:
        # Option already registered, ignore
        pass


@pytest.fixture(scope='session')
def hw_cluster_name(pytestconfig: pytest.Config) -> str:
    """Fixture for hardware cluster name. Returns the value from --hw-cluster option."""
    cluster_name = pytestconfig.getoption('hw_cluster')
    if cluster_name is None:
        # Return a default value if not provided (for tests that don't need hardware)
        yield ""
    else:
        yield cluster_name


@pytest.fixture(scope='session')
def hw_config_path(pytestconfig: pytest.Config) -> Path:
    yield Path(pytestconfig.getoption('hw_config'))


@pytest.fixture(scope="session")
def session_ctxt(hw_config_path: Path) -> SessionContext:
    if hw_config_path.exists():
        _session_ctxt = SessionContext.from_json(hw_config_path)
        # Resolve clusters_json path - if it's relative, resolve it relative to rootdir (where pytest runs)
        if not _session_ctxt.clusters_json.is_absolute():
            resolved_path = Path(_session_ctxt.clusters_json).resolve()
            if resolved_path.exists():
                _session_ctxt.clusters_json = resolved_path
                _logger.info(f"Resolved clusters_json to: {_session_ctxt.clusters_json}")
            else:
                _logger.warning(f"clusters_json path does not exist: {resolved_path}")
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
            wpk_hostname = f"jlink{wpk.serial}.{session_ctxt.domain_name}"
            wpk_ip = socket.gethostbyname(wpk_hostname)
            _logger.info(f"wpk hostname: {wpk_hostname}, ip: {wpk_ip}")
            dev_wpks.append(
                DevWpk(session_ctxt, wpk.serial, wpk_ip, time_server=time_server)
            )
    yield DevCluster(hw_cluster_name, dev_wpks)


@pytest.fixture(scope='session', autouse=True)
def last_run_symlink(request: pytest.FixtureRequest) -> None:
    """Create or update the logs/lastRun symlink to point to the current session log directory."""
    try:
        session_log_dir = request.getfixturevalue('session_log_dir')
    except pytest.FixtureLookupError:
        yield
        return
    logs_base = Path.cwd() / 'logs'
    last_run = logs_base / 'lastRun'
    logs_base.mkdir(parents=True, exist_ok=True)
    if last_run.exists():
        last_run.unlink()
    # Relative link so lastRun remains valid if the logs directory is moved
    last_run.symlink_to(session_log_dir.name)
    _logger.info(f'lastRun -> {session_log_dir}')
    yield


@pytest.fixture(scope="function", autouse=True)
def updated_session_ctxt(session_ctxt: SessionContext, log_dir: Path) -> SessionContext:
    # the log_dir fixture MUST either be provided by another package or by a conftest.py file.
    session_ctxt.current_test_logdir = log_dir
    _logger.debug(f'current test log directory: {session_ctxt.current_test_logdir}')
    yield session_ctxt


@pytest.fixture(scope='function')
def device_factory(updated_session_ctxt: SessionContext, hw_cluster: DevCluster) -> DeviceFactory:
    factory = DeviceFactory(updated_session_ctxt, hw_cluster)
    yield factory
    factory.finalize()


@pytest.fixture(scope="function", autouse=True)
def hw_cluster_free_all_wpk(request: pytest.FixtureRequest):
    """Fixture to free all WPKs before and after each test.
    Only active if hw_cluster fixture is available and has devices.
    This fixture MUST run before device_factory to ensure WPKs are free."""
    # Check if hw_cluster is needed by checking if --hw-cluster was provided
    hw_cluster_name = request.config.getoption('hw_cluster', default=None)
    if not hw_cluster_name:
        # No hardware cluster specified, skip this fixture
        yield
        return
    
    # Try to get hw_cluster fixture - it may not be available for all tests
    hw_cluster = None
    try:
        hw_cluster = request.getfixturevalue('hw_cluster')
        _logger.info(f"hw_cluster_free_all_wpk: Retrieved hw_cluster fixture with {len(hw_cluster.wpk_list) if hw_cluster and hw_cluster.wpk_list else 0} WPKs")
    except Exception as e:
        # hw_cluster fixture not available for this test, skip this fixture
        # Catch all exceptions to be safe (not just FixtureLookupError/KeyError)
        _logger.debug(f"hw_cluster fixture not available for this test: {e}")
        yield
        return
    
    # Free all WPKs at the start of each test if cluster is available
    if hw_cluster and hw_cluster.wpk_list and len(hw_cluster.wpk_list) > 0:
        # Log the state before freeing
        reserved_count = sum(1 for wpk in hw_cluster.wpk_list if not wpk.is_free)
        _logger.info(f"[hw_cluster_free_all_wpk] BEFORE freeing: {reserved_count} reserved, {len(hw_cluster.wpk_list) - reserved_count} free out of {len(hw_cluster.wpk_list)} total")
        
        # Free all WPKs
        hw_cluster.free_all_wpk()
        
        # Verify all WPKs are now free
        free_count = sum(1 for wpk in hw_cluster.wpk_list if wpk.is_free)
        reserved_after = sum(1 for wpk in hw_cluster.wpk_list if not wpk.is_free)
        _logger.info(f"[hw_cluster_free_all_wpk] AFTER freeing: {free_count} free, {reserved_after} reserved out of {len(hw_cluster.wpk_list)} total")
        
        if reserved_after > 0:
            _logger.error(f"[hw_cluster_free_all_wpk] ERROR: {reserved_after} WPKs are still reserved after free_all_wpk()!")
            for i, wpk in enumerate(hw_cluster.wpk_list):
                _logger.error(f"  WPK[{i}]: serial={wpk.serial_no}, is_free={wpk.is_free}")
        
        hw_cluster.parallel_command('clear_flash')
        yield
        # Free all WPKs at the end of each test
        _logger.debug("[hw_cluster_free_all_wpk] Freeing WPKs after test")
        hw_cluster.free_all_wpk()
    else:
        _logger.warning(f"hw_cluster has no WPKs: cluster={hw_cluster}, wpk_list={hw_cluster.wpk_list if hw_cluster else None}")
        yield


@pytest.fixture(scope="function", autouse=True)
def cleanup_background_processes():
    BackgroundProcess.stop_all()
    yield
    BackgroundProcess.stop_all()

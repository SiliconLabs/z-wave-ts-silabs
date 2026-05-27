Z-Wave Silabs Release Notes
===========================

Release v0.1
------------

- Supports WPK/WSTK control through admin interface (telnet port 4902)
- Supports Z-Wave sample apps CLI (telnet port 4901)
- Uses commander-cli to flash and get info on the radio board, to retrieve the Z-Wave DSK, etc.
- Added a way to do direct inclusion/exclusion devices (secured/unsecured)
- Added a way to use SmartStart through uic-upvl
- Added a way to OTA through uic-image-provider
- Added a way to control ZPC through MQTT
- Supports socat to get rid of the ubs connection between the ncp_serial_api_controller and ZPC
- Clean management of subprocesses, logs and configuration (zwave binaries location, bootloader keys, cluster description file location)
- Integrates with Pytest and the CI (fixtures and Junit report)

Release v0.2
------------

- Is now a pytest plugin, this means that a conftest.py is not needed to load fixtures anymore, they will automatically be launched by pytest
- Installs pytest-rerunfailures by default now
- Supports DCH/PTI parsing in both .pcap and .zlf files (pcap support is partial)
- Supports RTT traces using commander-cli (for now all the output from commander-cli is dumped, which is not the cleanest)
- Supports running UIC tools without needing access to /etc or /var
- Has a better look and feel for tests through the use introduction of a device_factory fixture for spawning nodes
- Has a better interface for choosing on which cluster should the current test session run on (--hw-cluster cli option)
- Supports macOS natively

Release v0.3
------------

- Removed automatic reset of WPK on each test
- Removed pytest-rerunfailures as it may actually hide some issues
- Has better DCH and PTI parsers, they were updated to be used in other projects
- Supports all Z-Wave regions
- Supports all NCP applications, their serial interfaces are exposed through socat
- Supports railtest application for frame injection among other use case

Release v0.4
------------

- Removed Zpc from the device_factory, it has to be instantiated manually in the test
- Removed DevZwaveNcpZnifferPti to match with the future removal of this app from the SiliconLabs Z-Wave SDK
- WPK IPs are now resolved once at the start of the test session
- Mosquitto MQTT broker and Zpc now use Unix Domain Sockets to communicate
- Helper scripts were added to the examples (DCH traffic dumping, zlf to pcap conversion, dump pcap content to csv)
- The fixture responsible for returning the log directory for the current session now returns a relative path

Release v0.5.1
------------

- ``hw_clusters`` accepts ``clusters.json`` with ``schema_version`` 1 (metadata keys such as ``$schema``, plus a ``clusters`` object with per-cluster ``devices`` arrays). The legacy top-level ``name -> [wpk, ...]`` map remains supported. Serial and board fields are validated on load (see ``clusters_json.load_clusters_json``).
- Z-Wave sample-app CLI communication uses TCP on port 4901 instead of Telnet (``_CliTcpSocket``, ``run_cmd``). CLI parsers accept an optional ``[I] `` log prefix. ``DevZwaveCli`` adds ``press()`` and ``em1_lock_rtt()``; WPK admin Telnet reconnects on pipe or connection reset.
- Traces and RTT logs are stored under a per-device subdirectory (``N_FriendlyName``). Zniffer and Railtest skip automatic capture folders. ``ZlfFileWriter`` supports size-based rotation with optional gzip and helpers to list rotated files.
- Root ``config.json``, ``conftest.py``, ``pytest.ini``, and ``setup_dev_environment.py`` support local runs. Dev Container, Conan remotes, artifact fetch scripts, ``pick_hw_cluster.py``, and VS Code tasks are included for development setup.
- Pytest options ``--pti`` and ``--rtt`` enable PTI and RTT capture per test (disabled by default in ``SessionContext``).
- SOC devices support ``wpk_serial_speed="auto"``: baud rate is read from WPK admin TCP port 4902 (``serial vcom``). NCP device types reject ``"auto"``.

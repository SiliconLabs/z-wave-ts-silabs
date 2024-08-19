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

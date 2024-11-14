# z_wave_ts_silabs

The purpose of this project is to provide tools to control SiliconLabs Z-Wave devices.
One usage it to run the ZWA test suite and validate our embedded software,
testing coverage can be factorized among ZWA members.

## Setup

```bash
virtualenv .venv # or: python -m venv .venv
.venv/bin/pip wheel --no-deps -w dist . && .venv/bin/pip install z_wave_ts_silabs -f ./dist # or: .venv/bin/pip install -r requirements.txt
cd examples/ && ./run_tests.sh manual-0 test_script.py
```

## Update

```bash
.venv/bin/pip uninstall z_wave_ts_silabs -y
rm -rf build/ dist/ z_wave_ts_silabs.egg-info/ # note: pip will always take the highest version in dist/
.venv/bin/pip wheel --no-deps -w dist . && .venv/bin/pip install z_wave_ts_silabs -f ./dist
```

## Use of Simplicity Commander

The `DevWpk` class uses commander-cli to interact with WPKs and radio boards

it can be downloaded for Linux, MacOS and Windows:
- https://www.silabs.com/documents/public/software/SimplicityCommander-Linux.zip
- https://www.silabs.com/documents/public/software/SimplicityCommander-Mac.zip
- https://www.silabs.com/documents/public/software/SimplicityCommander-Windows.zip

on Linux 	it should be installed in `/opt/silabs/commander-cli/commander-cli`
on macOS 	it should be installed in `/Applications/Commander-cli.app/Contents/MacOS/commander-cli`
on Windows 	it should be installed in `C:\Program Files\Simplicity Commander CLI\commander-cli.exe`

## ZPC

ZPC is the Z-Wave gateway supported by Silicon Labs, in order to remove constraints on one wpk being
linked to an RPi in the cluster we are redirecting TCP traffic from the WPK 4901 port to a virtual tty acting like 
a serial port. This way we can instantiate more than one gateway from a cluster.

## Setup on host machine

A `uic.cfg` file will be created in every test log folder. It will be used by every uic tools used in this test
framework, namely: ZPC, uic-upvl (SmartStart provisioning) and uic-image-provider (OTA updates).

A `uic-image-provider` folder will be created in every test log folder. 
It will be used by uic-image-provider to load `images.json` which
contains a list describing the update files available. The test framework will copy these files
in `uic-image-provider/updates`.

## Troubleshooting

If for any reason a test was interrupted by a signal during a call to commander-cli.
then there might a hanging process in the background and the target board might be
inaccessible until it's been reset.

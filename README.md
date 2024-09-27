# z_wave_ts_silabs

## Setup

```bash
virtualenv .venv # or: python -m venv .venv
.venv/bin/pip install -r requirements.txt
./run_tests.sh
```

## Use of Simplicity Commander

The `DevWpk` class uses commander-cli to interact with WPKs and radio boards

it can be downloaded for Linux, MacOS and Windows:
- https://www.silabs.com/documents/public/software/SimplicityCommander-Linux.zip
- https://www.silabs.com/documents/public/software/SimplicityCommander-Mac.zip
- https://www.silabs.com/documents/public/software/SimplicityCommander-Windows.zip

## ZPC

ZPC is the Z-Wave gateway supported by Silicon Labs, in order to remove constraints on one wpk being
linked to an RPi in the cluster we are redirecting TCP traffic from the WPK 4901 port to a virtual tty acting like 
a serial port. This way we can instantiate more than one gateway from a cluster.

## Setup on host machine

first create these folders for the user that will run the tests:

```
sudo mkdir -p /etc/uic
sudo chown -R user:group /etc/uic

sudo mkdir -p /var/lib/uic
sudo chown -R user:group /var/lib/uic

sudo mkdir -p /var/lib/uic-image-updater
sudo chown -R user:group /var/lib/uic-image-updater
```

`/etc/uic` will be used to create `uic.cfg` for every uic tools used in this test
framework, namely: ZPC, uic-upvl (SmartStart provisioning) and uic-image-updater (OTA updates).

`/var/lib/uic` is used to store zpc related files, the test framework stores by default the zpc and sapi logs there.

`/var/lib/uic-image-updater` is used by uic-image-updater to load `images.json` which
contains a list describing the update files available. The test framework will copy these files
in `/var/lib/uic-image-updater/updates`. The test framework should wipe the updates folder 
everytime.

## Rpi

the Rpi are set up to act as button manipulators. the idea is to control them remotely using pigpiod.

`systemctl enable --now pigpiod.service`

on the WPK expander pins the buttons are mapped like this:

- BTN0: EXP7
- BTN1: EXP9
- BTN2: EXP15
- BTN3: EXP16

NOTE: we could run ZPC directly on the Pi as executors as well, using socat.

## Troubleshooting

If for any reason a test was interrupted by a signal during a call to commander-cli.
then there might a hanging process in the background and the target board might be
inaccessible until it's been reset.

from __future__ import annotations
import os
import platform
import re
import json
import time
import shlex
import base64
import shutil
import socket
import hashlib
import logging
import threading
from typing import TextIO
from pathlib import Path
from datetime import datetime
from subprocess import Popen, PIPE, STDOUT, DEVNULL

from .session_context import SessionContext


_logger = logging.getLogger(__name__)


class BackgroundProcess(object):

    _process_list: list[BackgroundProcess] = []

    @staticmethod
    def are_all_patterns_matched(patterns: dict[str, re.Match | None] | None) -> bool:
        if patterns is None:
            return True

        if None in patterns.values():
            return False
        return True

    @staticmethod
    def pattern_matching(patterns: dict[str, re.Match | None] | None, log_file: TextIO):
        if patterns is None:
            return

        for line in log_file.readlines():
            for p in patterns.keys():
                m = re.search(p, line)
                if m is not None:
                    patterns[p] = m

    @staticmethod
    def stop_all():
        while len(BackgroundProcess._process_list) != 0:
            bg_proc = BackgroundProcess._process_list.pop()
            bg_proc.stop()

    @staticmethod
    def register(process: BackgroundProcess):
        if process not in BackgroundProcess._process_list:
            BackgroundProcess._process_list.append(process)

    # patterns dict keys must be set to None
    def __init__(self, ctxt: SessionContext, name: str, cmd_line: str, patterns: dict[str, re.Match | None] = None, timeout: float = 10):
        self._name = name
        self._ctxt = ctxt
        self._process: Popen | None = None
        self._thread: threading.Thread | None = None
        self.log_file_path = f"{self._ctxt.current_test_logdir}/{self._name}.log"
        self.wo_log_file = open(self.log_file_path, 'w')
        self.ro_log_file = open(self.log_file_path, 'r')

        _logger.debug(cmd_line)
        # create thread to start background process
        self._thread = threading.Thread(target=self._start_process_in_thread, args=(cmd_line,))
        self._thread.daemon = True
        self._thread.start()

        end_time = time.time() + timeout
        while time.time() < end_time:
            if not self.is_alive:
                continue
            if BackgroundProcess.are_all_patterns_matched(patterns):
                break
            else:
                BackgroundProcess.pattern_matching(patterns, self.ro_log_file)

        # if process is still alive add it to the module list, test fixtures can then be used to kill background processes
        if self.is_alive:
            BackgroundProcess.register(self)
        # otherwise just log the event that the process has died, it's the caller responsibility to check
        # if the process is still alive with BackgroundProcess.is_alive
        else:
            _logger.debug(f"process: {self._name} died")

    # there's no equivalent start() function because the constructor starts the process right away
    def stop(self):
        self.wo_log_file.close()
        self.ro_log_file.close()

        if self._process:
            self._process.kill()
            self._process.wait(1)  # 1 second should be enough to kill a process
            self._process = None

        # check that the thread that spawned the process has ended
        if self._thread and not self._thread.is_alive():
            self._thread = None

    def _start_process_in_thread(self, cmd_line: str):
        self._process = Popen(
            shlex.split(cmd_line),
            stdin=DEVNULL,
            stdout=self.wo_log_file,
            stderr=STDOUT,
        )
        self._process.wait()  # wait is a blocking call, this thread should stop after that

    @property
    def is_alive(self) -> bool:
        if self._process:
            if self._process.poll() is None:
                return True
        return False


class CommanderCli(object):

    def __init__(self, ctxt: SessionContext, ip: str) -> None:
        self._ctxt = ctxt
        self.ip: str = ip

        if not os.path.exists(ctxt.commander_cli):
            raise Exception('commander-cli not found on system')
        self._commander_cli_path = ctxt.commander_cli
        self._rtt_logger_background_process: BackgroundProcess | None = None

    def _run_commander_cli(self, cmd) -> str:
        cmd_output = ''
        cmd_line = f"{self._commander_cli_path} {cmd} --ip {self.ip}"  # TODO: the --device should be provided to CommanderCli when instantiated to provide help on some intermittent issues
        p = Popen(
            shlex.split(cmd_line),
            stdin=DEVNULL,
            stdout=PIPE,
            stderr=STDOUT,
            text=True
        )
        for line in p.stdout:
            cmd_output += line
        p.wait()
        if p.returncode != 0:
            _logger.error(f'+ {cmd_line}')
            _logger.error(cmd_output)
            raise Exception(f'commander-cli FAILED with exit code {p.returncode}\n{cmd_line}\n{cmd_output}')
        _logger.debug(f'commander-cli: {cmd_line}')
        return cmd_output

    def device_info(self):
        return self._run_commander_cli('device info')

    def device_recover(self):
        return self._run_commander_cli('device recover')

    def device_pageerase(self, region: str):
        return self._run_commander_cli(f'device pageerase --region {region}')

    def flash(self, firmware_path):
        return self._run_commander_cli(f'flash {firmware_path}')

    def flash_token(self, token_group: str, token: str):
        return self._run_commander_cli(f'flash --tokengroup {token_group} --token {token}')

    def flash_tokenfiles(self, token_group: str, token_files: tuple):
        cmd_line = f'flash --tokengroup {token_group}'
        for tkfile_path in token_files:
            cmd_line += f' --tokenfile {tkfile_path}'
        return self._run_commander_cli(cmd_line)

    def spawn_rtt_logger_background_process(self, process_name: str):
        cmd_line = f"{self._commander_cli_path} rtt connect --noreset --ip {self.ip}"
        self._rtt_logger_background_process = BackgroundProcess(ctxt=self._ctxt, name=process_name, cmd_line=cmd_line)

    def kill_rtt_logger_background_process(self):
        if self._rtt_logger_background_process:
            self._rtt_logger_background_process.stop()
            self._rtt_logger_background_process = None


class Mosquitto(BackgroundProcess):

    def __init__(self, ctxt: SessionContext) -> None:
        mosquitto_path = shutil.which('mosquitto', path=os.environ['PATH']+':/usr/sbin')
        if mosquitto_path is None:
            raise Exception('mosquitto not found on system')

        super().__init__(ctxt, 'mosquitto', mosquitto_path)


class MosquittoSub(BackgroundProcess):

    def __init__(self, ctxt: SessionContext, topic: str = 'ucl/#'):
        mosquitto_sub_path = shutil.which('mosquitto_sub', path=os.environ['PATH']+':/usr/sbin')
        if mosquitto_sub_path is None:
            raise Exception('mosquitto_sub not found on system')

        cmd_line = f"{mosquitto_sub_path} -F '@Y-@m-@d @H:@M:@S %t %p' -t '{topic}'"
        # naming the process 'mqtt' so that the log file bears the name mqtt.log
        super().__init__(ctxt, 'mqtt', cmd_line)


class Socat(BackgroundProcess):

    def __init__(self, ctxt: SessionContext, hostname: str, port: int):
        socat_path = shutil.which('socat', path=os.environ['PATH']+':/usr/sbin')
        if socat_path is None:
            raise Exception('socat not found on system')

        pty_path_regex = r"PTY is (?P<pty>(\/dev\/.+))"
        self.patterns = {
            pty_path_regex: None
        }
        cmd_line = f"{socat_path} -x -v -dd TCP:{hostname}:{port},nodelay PTY,rawer,sane"
        super().__init__(ctxt, f'socat-{hostname}', cmd_line, self.patterns)
        if self.patterns[pty_path_regex] is not None:
            self.pty_path = self.patterns[pty_path_regex].groupdict()['pty']
        else:
            raise Exception(f"could not find pattern: '{pty_path_regex}' in socat output")


class UicUpvl(BackgroundProcess):

    def __init__(self, ctxt: SessionContext):
        # the ZPC background process is in charge of creating this configuration file
        uic_config_file_path = f"{ctxt.current_test_logdir}/uic.cfg"
        if not os.path.exists(uic_config_file_path):
            raise FileNotFoundError

        cmd_line = f'{ctxt.uic}/uic-upvl --conf {uic_config_file_path}'
        super().__init__(ctxt, 'upvl', cmd_line)


class UicImageProvider(BackgroundProcess):

    @staticmethod
    def md5_base64(file: str) -> str | None:
        with open(file, 'rb') as f:
            md5_hash = hashlib.md5(f.read())
            return base64.b64encode(md5_hash.digest()).decode()

    def __init__(self, ctxt: SessionContext, devices_to_update: list[dict[str, str]]):
        # the ZPC background process is in charge of creating this configuration file
        uic_config_file_path = f"{ctxt.current_test_logdir}/uic.cfg"
        if not os.path.exists(uic_config_file_path):
            raise FileNotFoundError

        # devices_to_update format is 
        # [
        #   {
        #       "file": str,
        #       "uiid": str,
        #       "unid": str
        #   },
        #   ...
        # ]
        self.updates_dir_path = f'{ctxt.current_test_logdir}/uic-image-provider/updates'
        self.images_file_path = f'{ctxt.current_test_logdir}/uic-image-provider/images.json'
        self.images_json = {
            "Version": "1",
            "Images": []
        }

        # there's a mapping between app and Product type part of UIID
        # see OTA UIID Construction in: https://siliconlabs.github.io/UnifySDK/applications/zpc/readme_user.html

        # create the updates/ folder and the images.json file
        os.mkdir(f'{ctxt.current_test_logdir}/uic-image-provider/')
        os.mkdir(self.updates_dir_path)
        with open(self.images_file_path, 'w') as f:

            for dev in devices_to_update:
                file = dev['file']
                uuid = dev['uiid']
                unid = dev['unid']
                version = dev['version']

                src_path = f'{ctxt.zwave_binaries}/{file}'
                dst_path = f'{self.updates_dir_path}/{file}'
                images_entry = {
                    "FileName": f"updates/{file}",
                    "Uiid": uuid,
                    "Unid": [unid],
                    "Version": version,
                    "ApplyAfter": "2000-01-01T10:00:00+02:00",
                    # date is set way back so that the update starts right away
                    "Md5": UicImageProvider.md5_base64(f'{ctxt.zwave_binaries}/{file}')
                }
                self.images_json["Images"].append(images_entry)
                shutil.copyfile(src_path, dst_path)

            _logger.debug(f'uic-image-provider: images.json: {self.images_json}')
            f.write(json.dumps(self.images_json))

        cmd_line = f'{ctxt.uic}/uic-image-provider --conf {uic_config_file_path}'
        super().__init__(ctxt,'image_provider', cmd_line)


class Zpc(BackgroundProcess):

    def __init__(self, ctxt: SessionContext, region: str, tty_path: str, update_file: str | None = None):

        self.mqtt_main_process: Mosquitto | None = None
        self.mqtt_logs_process: MosquittoSub | None = None
        self.tty_path: str = tty_path

        uic_config_file_path = f"{ctxt.current_test_logdir}/uic.cfg"
        with open(uic_config_file_path, "w") as uic_cfg:
            uic_cfg.write(self._generate_uic_configuration_file(
                ctxt=ctxt,
                region=region.replace('REGION_', ''),
                log_level='d',
                tx_power='0',
                protocol_pref='2,1' if 'LR' in region else '1,2'
            ))

        cmd_line = f'{ctxt.uic}/zpc --conf {uic_config_file_path}'
        if update_file is not None:
            sapi_ver_regex = r"\[zpc_ncp_update\] chip_serial_api_version: (?P<sapiver>(7.\d{1,3}.\d{1,3}))"
            self.patterns = {
                sapi_ver_regex: None,
                r"\[zpc_ncp_update\] Re-booting into the bootloader": None,
                r"\[uic_gbl_interface\] Transmission is done": None,
                r"\[uic_component_fixtures\] Startup sequence aborted by: ZPC NCP update": None
            }
            cmd_line += f' --zpc.ncp_update {ctxt.zwave_binaries}/{update_file}'
            # OTW should not take more than 30 seconds, giving it a minute is more than enough
            super().__init__(ctxt,'zpc_ncp_update', cmd_line, self.patterns, 60)
            if self.patterns[sapi_ver_regex] is not None:
                self.sapi_version = self.patterns[sapi_ver_regex].groupdict()['sapiver']
                _logger.debug(f'OTW Serial API version: {self.sapi_version}')
            else:
                raise Exception(f"could not find pattern: '{sapi_ver_regex}' in zpc output")

            if self.patterns[r"\[uic_gbl_interface\] Transmission is done"] is None:
                raise Exception(f"OTW failed, check zpc_ncp_update.log")
        else:
            # it's useless to start mosquitto if we're doing an update of the ncp
            # that's why we only start it here
            self._start_mqtt_processes(ctxt)

            zpc_info_regex = r"ZPC HomeID (?P<homeid>([A-F]|[0-9]){8}) - NodeID (?P<nodeid>(\d{1,3}))"
            self.patterns = {
                zpc_info_regex: None,
                r"We are connected to the MQTT broker.": None,
                r"Subscription to ucl\/by-unid\/zw-(([A-F]|[0-9]){8})-(\d{4})\/ProtocolController\/NetworkManagement\/Write successful": None
            }
            super().__init__(ctxt, 'zpc', cmd_line, self.patterns, 30)
            if self.patterns[zpc_info_regex] is not None:
                self.home_id = self.patterns[zpc_info_regex].groupdict()['homeid']
                self.node_id = self.patterns[zpc_info_regex].groupdict()['nodeid']
            else:
                raise Exception(f"could not find pattern: '{zpc_info_regex}' in zpc output")

    def _generate_uic_configuration_file(self, ctxt: SessionContext, region: str, log_level: str, tx_power: str, protocol_pref: str) -> str:
        uic_configuration = (
            f"# Unify configuration file (autogenerated on: {datetime.now()})\n"
            f"log:\n"
            f"  level: '{log_level}'\n"
            f"mapdir: '{ctxt.uic}/rules'\n"
            f"zpc:\n"
            f"  inclusion_protocol_preference: '{protocol_pref}'\n"
            f"  normal_tx_power_dbm: {tx_power}\n"
            f"  rf_region: '{region}'\n"
            f"  serial: '{self.tty_path}'\n"
            f"  serial_log_file: '{ctxt.current_test_logdir}/sapi.log'\n"
            f"  datastore_file: '{ctxt.current_test_logdir}/zpc.db'\n"
            f"  poll:\n"
            f"    attribute_list_file: '{ctxt.uic}/zwave_poll_config.yaml'\n"
            f"  ota:\n"
            f"    cache_path: '{ctxt.current_test_logdir}/zpc_ota_cache'\n"
            # maybe append this in the relevant processes instead ?
            f"upvl:\n"
            f"  datastore_file: '{ctxt.current_test_logdir}/upvl.db'\n"
            f"image_provider:\n"
            f"  image_path: '{ctxt.current_test_logdir}/uic-image-provider'\n"
        )

        return uic_configuration


    def _start_mqtt_processes(self, ctxt: SessionContext) -> None:
        self.mqtt_main_process = Mosquitto(ctxt)
        if not self.mqtt_main_process.is_alive:
            raise Exception("mosquitto process did not start or died unexpectedly")
        self.mqtt_logs_process = MosquittoSub(ctxt)
        if not self.mqtt_logs_process.is_alive:
            raise Exception("mosquitto_sub process did not start or died unexpectedly")

    def stop(self):
        super().stop()
        if self.mqtt_logs_process is not None:
            self.mqtt_logs_process.stop()
        if self.mqtt_main_process is not None:
            self.mqtt_main_process.stop()

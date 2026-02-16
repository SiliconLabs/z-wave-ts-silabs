#!/usr/bin/env python3
"""Setup commander-cli and conan via SLT"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

class Colors:
    GREEN, RED, YELLOW, ORANGE, CYAN, NC = '\033[92m', '\033[91m', '\033[93m', '\033[38;5;208m', '\033[96m', '\033[0m'

class ToolsSetup:
    def __init__(self):
        self.slt_path = Path.home() / ".local" / "bin" / "slt"
        self.commander_tool = "commander"
        self.commander_binary = "commander"
        self.conan_tool = "conan"
        self.conan_binary = "conan"

    def log(self, package: str, status: str, message: str = ""):
        if status == "progress":
            print(f"\r\033[K{package}: {message}...", end="", flush=True)
        elif status == "done":
            print(f"\r\033[K{Colors.GREEN}✓{Colors.NC} {package}: {message}")
        elif status == "fail":
            print(f"\r\033[K{Colors.RED}✗{Colors.NC} {package}: {message}")
        elif status == "status":
            icon = f"{Colors.GREEN}✓{Colors.NC}" if message else f"{Colors.RED}✗{Colors.NC}"
            print(f"{package + ':':<15} {icon} {message}")

    def slt_package_exists(self, tool_name: str) -> bool:
        if not self.slt_path.is_file() or not os.access(self.slt_path, os.X_OK):
            return False
        try:
            result = subprocess.run([str(self.slt_path), "where", tool_name], 
                                  capture_output=True, text=True, check=True)
            return bool(result.stdout.strip())
        except subprocess.CalledProcessError:
            return False

    def get_version(self, binary: str, version_cmd: str) -> str | None:
        try:
            result = subprocess.run([binary, version_cmd], 
                                  capture_output=True, text=True, check=True)
            output = result.stdout.strip()

            for line in output.split('\n'):
                line = line.strip()
                if not line:
                    continue

                patterns = [
                    r'\b(\d+v\d+p\d+b\d+)\b',  # Commander format
                    r'\b(\d+\.\d+\.\d+[\.\-_]\d+[\w\.\-]*)\b',  # Semantic with build number
                    r'\b(\d+\.\d+\.\d+)\b',  # Standard semantic (X.Y.Z)
                ]
                for pattern in patterns:
                    match = re.search(pattern, line)
                    if match:
                        return match.group(1)
                return line
            return None
        except subprocess.SubprocessError:
            return None

    def find_tool_binary(self, tool_name: str, binary_name: str) -> str | None:
        try:
            result = subprocess.run([str(self.slt_path), "where", tool_name], 
                                  capture_output=True, text=True, check=True)
            tool_base_path = result.stdout.strip()
            if tool_base_path:
                find_result = subprocess.run(["find", tool_base_path, "-name", binary_name, 
                                            "-type", "f", "-executable"], 
                                           capture_output=True, text=True, check=True)
                binaries = find_result.stdout.strip().split('\n')
                return binaries[0] if binaries and binaries[0] else None
        except subprocess.CalledProcessError:
            pass
        return None

    def update_profile(self, var_name: str, var_value: str, comment: str = "", is_path: bool = False):
        config_path = Path.home() / ".bashrc"
        export_line = f"export PATH=\"{var_value}:$PATH\"" if is_path else f"export {var_name}=\"{var_value}\""

        if config_path.exists():
            content = config_path.read_text()
            pattern = f"export PATH=.*{re.escape(var_value)}" if is_path else f"export {var_name}="
            if not re.search(pattern, content):
                with config_path.open('a') as f:
                    f.write(f"\n# {comment or 'Added by setup'}\n{export_line}\n")

        if is_path:
            os.environ['PATH'] = f"{var_value}:{os.environ.get('PATH', '')}"
        else:
            os.environ[var_name] = var_value

    def configure_tool_env(self, tool_name: str):
        result = subprocess.run([str(self.slt_path), "where", tool_name], 
                              capture_output=True, text=True)
        tool_base_path = result.stdout.strip() if result.returncode == 0 else ""

        if tool_name == "commander" and tool_base_path:
            commander_binary = str(Path(tool_base_path) / tool_name)
            self.update_profile("POST_BUILD_EXE", commander_binary, "Commander environment")

    def install_tool(self, tool_name: str, binary_name: str = None) -> bool:
        if binary_name is None:
            binary_name = tool_name
        
        display_name = tool_name.capitalize()
        self.log(display_name, "progress", "checking")

        try:
            # Always run install with --check-updates to handle both installation and updates
            subprocess.run([str(self.slt_path), "install", tool_name, "--check-updates"], 
                         capture_output=True, text=True, check=True)
            binary_path = self.find_tool_binary(tool_name, binary_name)
            if binary_path:
                self.update_profile("", str(Path(binary_path).parent), f"Path for {tool_name}", is_path=True)
                if tool_name == "commander":
                    self.configure_tool_env(tool_name)
                version_info = self.get_version(binary_path, "--version")
                self.log(display_name, "done", version_info or "installed")
                return True
        except subprocess.CalledProcessError as e:
            self.log(display_name, "fail", f"Installation failed: {e}")

        self.log(display_name, "fail", "Installation failed")
        return False

    def install_slt(self) -> bool:
        self.log("SLT", "progress", "checking")

        if self.slt_path.is_file() and os.access(self.slt_path, os.X_OK):
            try:
                subprocess.run([str(self.slt_path), "update", "--self"], 
                             check=True, capture_output=True)
            except subprocess.CalledProcessError:
                pass
            version_info = self.get_version(str(self.slt_path), "--version")
            if version_info:
                self.log("SLT", "done", version_info)
                return True

        self.log("SLT", "fail", "SLT not found. Please install SLT on the host and mount it.")
        return False

    def cmd_install(self):
        print(f"\n{Colors.CYAN}Z-Wave TS Silabs - Tools Setup{Colors.NC}\n{'='*38}")
        if not self.install_slt():
            sys.exit(1)
        if not self.install_tool(self.commander_tool, self.commander_binary):
            sys.exit(1)
        if not self.install_tool(self.conan_tool, self.conan_binary):
            sys.exit(1)
        print(f"{Colors.GREEN}✓{Colors.NC} Setup completed successfully!\n")

    def cmd_status(self):
        print("Tools Installation Status\n==============================")

        slt_installed = self.slt_path.is_file() and os.access(self.slt_path, os.X_OK)
        version_info = self.get_version(str(self.slt_path), "--version") if slt_installed else None
        status = f"{Colors.GREEN}✓{Colors.NC} {version_info}" if version_info else f"{Colors.RED}✗{Colors.NC} Not installed"
        print(f"{'SLT:':<15} {status}")

        # Commander status
        if self.slt_package_exists(self.commander_tool):
            binary_path = self.find_tool_binary(self.commander_tool, self.commander_binary)
            version_info = self.get_version(binary_path, "--version") if binary_path else None
            status = f"{Colors.GREEN}✓{Colors.NC} {version_info}" if version_info else f"{Colors.RED}✗{Colors.NC} Binary not in PATH"
        else:
            status = f"{Colors.RED}✗{Colors.NC} Not installed"
        print(f"{'Commander:':<15} {status}")

        # Conan status
        if self.slt_package_exists(self.conan_tool):
            binary_path = self.find_tool_binary(self.conan_tool, self.conan_binary)
            version_info = self.get_version(binary_path, "--version") if binary_path else None
            status = f"{Colors.GREEN}✓{Colors.NC} {version_info}" if version_info else f"{Colors.RED}✗{Colors.NC} Binary not in PATH"
        else:
            status = f"{Colors.RED}✗{Colors.NC} Not installed"
        print(f"{'Conan:':<15} {status}")

    def run(self):
        parser = argparse.ArgumentParser(description="Tools Setup Script (Commander and Conan)")
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument("--install", action="store_true", help="Install commander-cli and conan")
        group.add_argument("--status", action="store_true", help="Show installation status")
        args = parser.parse_args()

        if args.install:
            self.cmd_install()
        elif args.status:
            self.cmd_status()

if __name__ == "__main__":
    ToolsSetup().run()

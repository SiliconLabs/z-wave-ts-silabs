#!/usr/bin/env python3
"""Setup Z-Wave test framework with enhanced display"""

import os, shutil, subprocess, sys, threading, time
from pathlib import Path

class Colors:
    GREEN, RED, YELLOW, ORANGE, CYAN, NC = '\033[92m', '\033[91m', '\033[93m', '\033[38;5;208m', '\033[96m', '\033[0m'

def log(message: str, status: str = "info", indent: bool = True):
    """Log with status icons"""
    icons = {"info": f"{Colors.CYAN}➤{Colors.NC}", "ok": f"{Colors.GREEN}✓{Colors.NC}",
             "fail": f"{Colors.RED}✗{Colors.NC}", "warn": f"{Colors.YELLOW}⚠{Colors.NC}",
             "skip": f"{Colors.ORANGE}⊘{Colors.NC}"}
    prefix = "  " if indent else ""
    print(f"{prefix}{icons[status]} {message}")

def run_with_spinner(cmd: str, cwd: str = None, section: str = "Processing") -> bool:
    """Run command with spinner and step detection"""
    chars = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    print(f"  {Colors.CYAN}➤{Colors.NC} {section}", end="", flush=True)

    try:
        process = subprocess.Popen(cmd, shell=True, cwd=cwd, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, text=True, bufsize=1)

        spinner_active = True
        def update_spinner():
            while spinner_active:
                char = chars[int(time.time() * 10) % len(chars)]
                print(f"\r  {Colors.CYAN}{char}{Colors.NC} {section}  ", end="", flush=True)
                time.sleep(0.1)

        threading.Thread(target=update_spinner, daemon=True).start()
        process.wait()
        spinner_active = False

        if process.returncode == 0:
            print(f"\r  {Colors.GREEN}✓{Colors.NC} {section}")
            return True
        else:
            print(f"\r  {Colors.RED}✗{Colors.NC} {section} - Command failed")
            return False
    except Exception as e:
        print(f"\r  {Colors.RED}✗{Colors.NC} {section} - Error: {e}")
        return False

def ensure_github_known_hosts():
    """Ensure GitHub is in SSH known_hosts"""
    try:
        if subprocess.run(["ssh-keygen", "-F", "github.com"], capture_output=True).returncode == 0:
            return True
        result = subprocess.run(["ssh-keyscan", "-H", "github.com"], capture_output=True, text=True, check=True)
        (Path.home() / ".ssh").mkdir(exist_ok=True)
        (Path.home() / ".ssh" / "known_hosts").open("a").write(result.stdout)
        return True
    except (subprocess.CalledProcessError, OSError):
        return False

def setup_test_environment():
    """Setup Z-Wave test framework with enhanced display"""
    log("Starting test environment setup", "info", indent=False)

    # Ensure GitHub is in known_hosts before cloning
    if not ensure_github_known_hosts():
        log("Failed to add GitHub to known_hosts", "warn")

    test_path = "z-wave-test-system"
    test_path_obj = Path(test_path)
    
    # Check if directory exists and contains a valid git repository
    if test_path_obj.exists() and (test_path_obj / ".git").exists():
        log("z-wave-test-system directory already exists with git repository, skipping clone", "ok")
        # Install packages in editable mode (order matters: generator -> wave -> wave_ts).
        # Use --no-build-isolation for all so builds use the current env (z_wave_generator is not on PyPI).
        commands = [
            ("python3 -m pip install --user --no-build-isolation -e .", f"{test_path}/z_wave_generator", "Installing z_wave_generator (editable)"),
            ("python3 -m pip install --user --no-build-isolation -e .", f"{test_path}/z_wave", "Installing z_wave (editable)"),
            ("python3 -m pip install --user --no-build-isolation -e .", f"{test_path}/z_wave_ts", "Installing z_wave_ts (editable)"),
            (f"python3 -m pip install --user -r {test_path}/z_wave_ts/requirements.txt", None, "Installing z_wave_ts dependencies")
        ]
    else:
        # Directory doesn't exist or is not a git repo, clone it
        if test_path_obj.exists():
            shutil.rmtree(test_path, ignore_errors=True)
            log("Cleaned up existing installation", "ok")

        Path(test_path).parent.mkdir(parents=True, exist_ok=True)

        # Use --no-build-isolation for all packages so builds use the current env.
        commands = [
            (f"git clone git@github.com:SiliconLabs/z-wave-test-system.git {test_path} -b main", None, "Cloning test framework"),
            ("python3 -m pip install --user --no-build-isolation -e .", f"{test_path}/z_wave_generator", "Installing z_wave_generator (editable)"),
            ("python3 -m pip install --user --no-build-isolation -e .", f"{test_path}/z_wave", "Installing z_wave (editable)"),
            ("python3 -m pip install --user --no-build-isolation -e .", f"{test_path}/z_wave_ts", "Installing z_wave_ts (editable)"),
            (f"python3 -m pip install --user -r {test_path}/z_wave_ts/requirements.txt", None, "Installing z_wave_ts dependencies")
        ]

    for cmd, cwd_path, section in commands:
        if not run_with_spinner(cmd, cwd=cwd_path, section=section):
            return False

    log("Test environment setup completed successfully", "ok")
    return True

def main():
    """Main setup orchestrator"""
    print(f"\n{Colors.CYAN}Z-Wave Test Environment Setup{Colors.NC}\n{'='*38}")

    if not setup_test_environment():
        log("Test environment setup failed", "fail")
        sys.exit(1)

    print(f"\n{Colors.GREEN}✓{Colors.NC} Test environment setup completed successfully!")

if __name__ == "__main__":
    main()

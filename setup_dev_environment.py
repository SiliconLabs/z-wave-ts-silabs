#!/usr/bin/env python3
"""Setup Z-Wave development environment including Conan and test framework"""

import os, shutil, subprocess, sys, threading, time, re
from pathlib import Path

WORKSPACE_ROOT = "/home/zwave/workspace/zwave"

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

    spinner_active = False
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
        process.communicate()
        spinner_active = False

        if process.returncode == 0:
            print(f"\r  {Colors.GREEN}✓{Colors.NC} {section}")
            return True
        else:
            print(f"\r  {Colors.RED}✗{Colors.NC} {section} - Command failed")
            return False
    except Exception as e:
        spinner_active = False
        print(f"\r  {Colors.RED}✗{Colors.NC} {section} - Error: {e}")
        return False

def extract_version() -> str:
    """Extract version from zwave.slce file"""
    slce_file = Path(WORKSPACE_ROOT) / "zwave.slce"
    if not slce_file.exists():
        raise FileNotFoundError("zwave.slce file not found")

    match = re.search(r'^version:\s*(\d+\.\d+\.\d+)', slce_file.read_text(), re.MULTILINE)
    if match:
        return match.group(1)
    raise ValueError("Could not extract version")

def install_conan():
    """Install and configure Conan with enhanced display"""
    log("Starting Conan setup", "info", indent=False)

    try:
        subprocess.run(["conan", "--version"], capture_output=True, check=True)
        log("Conan is available", "ok")
    except (subprocess.CalledProcessError, FileNotFoundError):
        log("Conan is not available", "fail")
        return False

    try:
        version = extract_version()
        log(f"Detected Z-Wave version: {version}", "ok")
    except (FileNotFoundError, ValueError) as e:
        log(f"Version extraction failed: {e}", "fail")
        return False

    if not run_with_spinner("conan install .", cwd=WORKSPACE_ROOT, section="Installing Conan dependencies"):
        return False

    editable_cmd = f"conan editable add -nr --name=zwave --version={version} ."
    if not run_with_spinner(editable_cmd, cwd=WORKSPACE_ROOT, section="Adding editable Z-Wave package"):
        return False

    log("Conan setup completed successfully", "ok")
    return True

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

def setup_git_submodules(path=WORKSPACE_ROOT):
    """Initialize git submodules recursively if they don't have local changes"""
    if path == WORKSPACE_ROOT:
        log("Starting git submodules setup", "info", indent=False)
    
    # Get submodules from .gitmodules
    gitmodules_path = Path(path) / ".gitmodules"
    if not gitmodules_path.exists():
        if path == WORKSPACE_ROOT:
            log("No .gitmodules found, skipping", "info")
        return True
    
    submodules = []
    for line in gitmodules_path.read_text().split('\n'):
        if line.strip().startswith('path = '):
            submodules.append(line.split('=', 1)[1].strip())
    
    # Check each submodule for local changes
    for submodule in submodules:
        submodule_path = Path(path) / submodule
        
        if not submodule_path.exists():
            # Submodule doesn't exist - init recursively
            run_with_spinner(f"git submodule update --init --recursive {submodule}", cwd=path, section=f"Initializing {submodule}")
        else:
            # Submodule exists - check for local changes
            result = subprocess.run(["git", "status", "--porcelain"], cwd=submodule_path, capture_output=True, text=True)
            if result.returncode == 0 and result.stdout.strip():
                log(f"Submodule '{submodule}' has local changes - skipping", "skip")
                continue
            
            # No local changes - update and recurse manually
            run_with_spinner(f"git submodule update {submodule}", cwd=path, section=f"Updating {submodule}")
            setup_git_submodules(submodule_path)
    
    if path == WORKSPACE_ROOT:
        log("Git submodules setup completed", "ok")
    return True

def setup_test_environment():
    """Setup Z-Wave test framework with enhanced display"""
    log("Starting test environment setup", "info", indent=False)

    # Ensure GitHub is in known_hosts before cloning
    if not ensure_github_known_hosts():
        log("Failed to add GitHub to known_hosts", "warn")

    test_path = "z-wave-test-system"
    if os.path.exists(test_path):
        shutil.rmtree(test_path, ignore_errors=True)
        log("Cleaned up existing installation", "ok")

    Path(test_path).parent.mkdir(parents=True, exist_ok=True)

    commands = [
        (f"git clone git@github.com:SiliconLabs/z-wave-test-system.git {test_path} -b main", None, "Cloning test framework"),
        # Use --no-build-isolation for all so builds use the current env (z_wave_generator is not on PyPI)
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
    print(f"{Colors.CYAN}Z-Wave Development Environment Setup{Colors.NC}\n{'='*38}")

    if not setup_git_submodules():
        log("Git submodules setup failed", "fail")
        sys.exit(1)

    if not install_conan():
        log("Conan setup failed", "fail")
        sys.exit(1)

    if not setup_test_environment():
        log("Test environment setup failed", "fail")
        sys.exit(1)

    print(f"\n{Colors.GREEN}✓{Colors.NC} Development environment setup completed successfully!")

if __name__ == "__main__":
    main()
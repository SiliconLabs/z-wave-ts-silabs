#!/usr/bin/env python3
"""Setup Z-Wave repository with sparse checkout"""

import os
import subprocess
import sys
import threading
import time
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

def run_git_command(cmd: list[str], cwd: Path, check: bool = True) -> tuple[bool, str]:
    """Run git command and return success status and output"""
    try:
        result = subprocess.run(
            ["git"] + cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=check
        )
        return True, result.stdout.strip()
    except subprocess.CalledProcessError as e:
        return False, e.stderr.strip()

def setup_sparse_checkout(z_wave_dir: Path, is_new_repo: bool = False) -> bool:
    """Setup sparse checkout configuration"""
    git_info_dir = z_wave_dir / ".git" / "info"
    git_info_dir.mkdir(parents=True, exist_ok=True)
    
    sparse_checkout_file = git_info_dir / "sparse-checkout"
    
    if is_new_repo:
        # Initial sparse checkout paths
        paths = [
            "/test/*",
            "/ci/tests/clusters.json",
            "/sample_apps/*-keys/*"
        ]
    else:
        # Updated sparse checkout paths
        paths = [
            "test/*",
            "ci/tests/*"
        ]
    
    # Write sparse checkout file
    sparse_checkout_file.write_text("\n".join(paths) + "\n")
    
    # Enable sparse checkout
    success, _ = run_git_command(["config", "core.sparseCheckout", "true"], z_wave_dir)
    if not success:
        log("Failed to enable sparse checkout", "fail")
        return False
    
    return True

def initialize_z_wave_repo(workspace_dir: Path, z_wave_dir: Path) -> bool:
    """Initialize z-wave repository with sparse checkout"""
    log("Z-wave directory does not exist. Setting up sparse checkout...", "info")
    
    # Create the z-wave directory
    z_wave_dir.mkdir(parents=True, exist_ok=True)
    
    # Initialize git repository
    if not run_with_spinner("git init", cwd=str(z_wave_dir), section="Initializing git repository"):
        return False
    
    # Setup sparse checkout
    if not setup_sparse_checkout(z_wave_dir, is_new_repo=True):
        return False
    
    # Add remote
    if not run_with_spinner(
        "git remote add origin git@github.com:SiliconLabsInternal/z-wave.git",
        cwd=str(z_wave_dir),
        section="Adding remote"
    ):
        return False
    
    # Fetch and checkout
    if not run_with_spinner(
        "git fetch origin main",
        cwd=str(z_wave_dir),
        section="Fetching from origin"
    ):
        return False
    
    if not run_with_spinner(
        "git checkout -b main origin/main",
        cwd=str(z_wave_dir),
        section="Checking out main branch"
    ):
        return False
    
    log("Submodule initialized with sparse checkout configured", "ok")
    return True

def update_existing_repo(z_wave_dir: Path) -> bool:
    """Update existing z-wave repository"""
    log("Z-wave directory already exists, skipping update to preserve local changes", "ok")
    
    if not (z_wave_dir / ".git").exists():
        log("No .git directory found in z-wave", "warn")
        return True
    
    # Just check if sparse checkout is enabled, but don't force update
    success, output = run_git_command(["config", "core.sparseCheckout"], z_wave_dir, check=False)
    if not success or output != "true":
        log("Sparse checkout not enabled, but keeping existing directory as-is", "info")
    
    # Don't fetch or update to preserve local modifications
    log("Using existing z-wave repository without updates", "ok")
    return True

def ensure_clusters_json(z_wave_dir: Path, clusters_json_path: Path) -> bool:
    """Ensure clusters.json file exists"""
    if clusters_json_path.exists():
        log(f"File {clusters_json_path.name} already exists", "ok")
        return True
    
    log(f"File {clusters_json_path.name} does not exist. Updating repository...", "info")
    
    # Update the repository
    if not run_with_spinner(
        "git fetch origin main",
        cwd=str(z_wave_dir),
        section="Fetching updates"
    ):
        return False
    
    # Try to checkout main branch
    success, _ = run_git_command(["checkout", "main"], z_wave_dir, check=False)
    if not success:
        if not run_with_spinner(
            "git checkout -b main origin/main",
            cwd=str(z_wave_dir),
            section="Creating main branch"
        ):
            return False
    
    if not run_with_spinner(
        "git sparse-checkout reapply",
        cwd=str(z_wave_dir),
        section="Reapplying sparse checkout"
    ):
        return False
    
    # Check again if the file exists after update
    if not clusters_json_path.exists():
        log(f"File {clusters_json_path.name} could not be retrieved automatically", "warn")
        success, output = run_git_command(["sparse-checkout", "list"], z_wave_dir, check=False)
        if success:
            log("Sparse checkout paths:", "info")
            for path in output.split("\n"):
                if path.strip():
                    print(f"    {path.strip()}")
        return False
    else:
        log(f"File {clusters_json_path.name} retrieved successfully", "ok")
        return True

def setup_zwave_repo():
    """Setup Z-Wave repository with sparse checkout"""
    log("Starting z-wave repository setup", "info", indent=False)
    
    # Get workspace directory
    script_dir = Path(__file__).parent
    workspace_dir = script_dir.parent.parent
    z_wave_dir = workspace_dir / "z-wave"
    clusters_json_path = z_wave_dir / "ci" / "tests" / "clusters.json"
    
    log(f"Workspace directory: {workspace_dir}", "info")
    log(f"Z-wave directory: {z_wave_dir}", "info")
    
    os.chdir(workspace_dir)
    
    # Check if z-wave directory exists
    if not z_wave_dir.exists():
        if not initialize_z_wave_repo(workspace_dir, z_wave_dir):
            return False
    else:
        if not update_existing_repo(z_wave_dir):
            return False
    
    # Ensure clusters.json exists
    ensure_clusters_json(z_wave_dir, clusters_json_path)
    
    log("Z-wave repository setup completed", "ok")
    return True

def main():
    """Main setup orchestrator"""
    print(f"\n{Colors.CYAN}Z-Wave Repository Setup{Colors.NC}\n{'='*38}")
    
    if not setup_zwave_repo():
        log("Z-wave repository setup failed", "fail")
        sys.exit(1)
    
    print(f"\n{Colors.GREEN}✓{Colors.NC} Z-wave repository setup completed successfully!")

if __name__ == "__main__":
    main()

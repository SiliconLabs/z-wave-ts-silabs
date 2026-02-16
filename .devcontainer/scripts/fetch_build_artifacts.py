#!/usr/bin/env python3
"""Fetch build artifacts from Conan and Artifactory"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
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

def run_with_spinner(cmd: str, cwd: str = None, section: str = "Processing") -> tuple[bool, str]:
    """Run command with spinner"""
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
        output, _ = process.communicate()
        spinner_active = False

        if process.returncode == 0:
            print(f"\r  {Colors.GREEN}✓{Colors.NC} {section}")
            return True, output
        else:
            print(f"\r  {Colors.RED}✗{Colors.NC} {section} - Command failed")
            return False, output
    except Exception as e:
        spinner_active = False
        print(f"\r  {Colors.RED}✗{Colors.NC} {section} - Error: {e}")
        return False, str(e)

def check_slt() -> bool:
    """Check if SLT is available"""
    slt_path = Path.home() / ".local" / "bin" / "slt"
    if not slt_path.is_file() or not os.access(slt_path, os.X_OK):
        log("SLT not found", "fail")
        log("Please ensure SLT is installed on the host and mounted correctly", "fail")
        return False
    return True

def check_conan() -> bool:
    """Check if Conan is available"""
    if shutil.which("conan"):
        return True
    
    log("Conan not found in PATH", "fail")
    log("Please run: python3 .devcontainer/scripts/setup_tools.py --install", "fail")
    return False

def configure_conan_remotes(workspace_dir: Path) -> tuple[bool, str]:
    """Configure Conan remotes from remotes.json"""
    remotes_file = workspace_dir / "remotes.json"
    
    if not remotes_file.exists():
        log(f"remotes.json not found at {remotes_file}", "fail")
        return False, ""
    
    try:
        with remotes_file.open() as f:
            data = json.load(f)
            remotes = data.get("remotes", [])
    except (json.JSONDecodeError, KeyError) as e:
        log(f"Failed to parse remotes.json: {e}", "fail")
        return False, ""
    
    if not remotes:
        log("No remotes found in remotes.json", "fail")
        return False, ""
    
    log(f"Configuring {len(remotes)} Conan remote(s)...", "info")
    
    configured_count = 0
    preferred_remote = ""
    
    for remote in remotes:
        name = remote.get("name", "")
        url = remote.get("url", "")
        
        if not name or not url:
            continue
        
        # Try to add the remote
        result = subprocess.run(
            ["conan", "remote", "add", name, url],
            capture_output=True, text=True
        )
        
        # Remote already exists is OK
        if result.returncode == 0 or "already exists" in result.stderr.lower():
            configured_count += 1
            # Prefer zwave-conan-dev or zwave-conan-dev-local for downloads
            if not preferred_remote or name in ["zwave-conan-dev", "zwave-conan-dev-local"]:
                preferred_remote = name
    
    if configured_count > 0:
        log(f"Configured {configured_count} Conan remote(s)", "ok")
        # Use preferred remote or first one as fallback
        remote_to_use = preferred_remote or remotes[0].get("name", "")
        return True, remote_to_use
    
    log("Failed to configure any Conan remotes", "fail")
    return False, ""

def get_package_version(workspace_dir: Path) -> str:
    """Get package version from conanfile.py"""
    if version := os.environ.get("PACKAGE_VERSION"):
        return version
    
    conanfile = workspace_dir / "conanfile.py"
    if conanfile.exists():
        content = conanfile.read_text()
        match = re.search(r'version\s*=\s*["\']([0-9]+\.[0-9]+\.[0-9]+)', content)
        if match:
            return match.group(1)
    
    log("Could not determine package version, using default 1.0.0", "warn")
    return "1.0.0"

def sanitize_channel(channel: str, z_wave_dir: Path) -> str:
    """Sanitize channel name - matches sanitize_conan_channel.sh behavior"""
    # Try to find the script: first in devcontainer/scripts/, then in z-wave/scripts/
    script_dir = Path(__file__).parent
    sanitize_script = script_dir / "sanitize_conan_channel.sh"
    
    if not sanitize_script.exists() or not os.access(sanitize_script, os.X_OK):
        sanitize_script = z_wave_dir / "scripts" / "sanitize_conan_channel.sh"
    
    if sanitize_script.exists() and os.access(sanitize_script, os.X_OK):
        try:
            result = subprocess.run([str(sanitize_script), channel], 
                                  capture_output=True, text=True, check=True)
            return result.stdout.strip()
        except subprocess.CalledProcessError:
            pass
    
    # Fallback sanitization: matches sanitize_conan_channel.sh exactly
    # 1. Convert to lowercase
    sanitized = channel.lower()
    
    # 2. Replace characters not in [a-z0-9_+.-] with underscore
    sanitized = re.sub(r'[^a-z0-9_+.-]', '_', sanitized)
    
    # 3. Replace leading character if not alphanumeric or underscore
    if sanitized and not re.match(r'^[a-z0-9_]', sanitized):
        sanitized = '_' + sanitized[1:]
    
    # 4. Limit to 100 characters
    sanitized = sanitized[:100]
    
    return sanitized

def get_package_channel(workspace_dir: Path, z_wave_dir: Path, branch_override: str | None = None) -> str:
    """Get package channel
    
    Args:
        workspace_dir: Workspace directory
        z_wave_dir: z-wave repository directory
        branch_override: Optional branch name to use (takes precedence over env var and git detection)
    """
    # Command line parameter takes highest precedence
    if branch_override:
        return sanitize_channel(branch_override, z_wave_dir)
    
    # Then environment variable
    if channel := os.environ.get("PACKAGE_CHANNEL"):
        return sanitize_channel(channel, z_wave_dir)
    
    # Try to get from z-wave repo git branch
    if (z_wave_dir / ".git").exists():
        try:
            result = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                                  cwd=z_wave_dir, capture_output=True, text=True, check=True)
            branch = result.stdout.strip() or "main"
            return sanitize_channel(branch, z_wave_dir)
        except subprocess.CalledProcessError:
            pass
    
    log("Could not determine package channel, using default 'main'", "warn")
    return "main"

def build_conan_ref(workspace_dir: Path, z_wave_dir: Path, branch_override: str | None = None) -> str:
    """Build Conan package reference (without recipe revision/SHA)
    
    Args:
        workspace_dir: Workspace directory
        z_wave_dir: z-wave repository directory
        branch_override: Optional branch name to use for package channel
    """
    package_name = "zwave_sample_app_internal"
    version = get_package_version(workspace_dir)
    
    # Normalize version to include '-0.dev' suffix if not present
    if not version.endswith("-0.dev"):
        version = f"{version}-0.dev"
    
    channel = get_package_channel(workspace_dir, z_wave_dir, branch_override)
    
    return f"{package_name}/{version}@silabs/{channel}"

def download_conan_metadata(package_ref: str, remote_name: str) -> bool:
    """Download Conan metadata"""
    success, _ = run_with_spinner(
        f'conan download "{package_ref}" -r {remote_name} --metadata="*" -vvv',
        section="Downloading Conan metadata"
    )
    return success

def get_metadata_folder(package_ref: str) -> Path | None:
    """Get metadata folder path"""
    try:
        result = subprocess.run(["conan", "cache", "path", package_ref, "--folder", "metadata"],
                              capture_output=True, text=True, check=True)
        path = result.stdout.strip()
        if path:
            return Path(path)
    except subprocess.CalledProcessError:
        pass
    return None

def clean_dist_bin(dist_bin: Path) -> bool:
    """Clean the dist/bin directory before downloading binaries"""
    if dist_bin.exists():
        log(f"Cleaning {dist_bin}...", "info")
        try:
            # Remove all files and subdirectories
            for item in dist_bin.iterdir():
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)
            log(f"Cleaned {dist_bin}", "ok")
        except Exception as e:
            log(f"Failed to clean {dist_bin}: {e}", "warn")
            return False
    else:
        # Create directory if it doesn't exist
        dist_bin.mkdir(parents=True, exist_ok=True)
        log(f"Created {dist_bin}", "ok")
    return True

def copy_binaries(metadata_folder: Path, dist_bin: Path) -> bool:
    """Copy binaries from metadata to dist/bin"""
    if not metadata_folder.exists() or not metadata_folder.is_dir():
        log(f"Metadata folder not found: {metadata_folder}", "fail")
        return False
    
    log("Copying binaries...", "info")
    
    dist_bin.mkdir(parents=True, exist_ok=True)
    copied_files = []
    
    # Copy .hex files
    for file in metadata_folder.glob("*.hex"):
        filename = file.name
        shutil.copy2(file, dist_bin / filename)
        copied_files.append(filename)
    
    # Copy .gbl files (v254 and v255)
    for pattern in ["*v254.gbl", "*v255.gbl"]:
        for file in metadata_folder.glob(pattern):
            filename = file.name
            shutil.copy2(file, dist_bin / filename)
            copied_files.append(filename)
    
    if copied_files:
        log(f"Copied {len(copied_files)} file(s)", "ok")
    else:
        log("No binaries found to copy", "warn")
    
    return True

def download_railtest_binaries(dist_bin: Path) -> bool:
    """Download railtest binaries from Artifactory (no authentication required)"""
    dist_bin.mkdir(parents=True, exist_ok=True)
    
    log("Downloading railtest binaries...", "info")
    
    downloaded_files = []
    base_url = "https://artifactory.silabs.net/artifactory/zwave-gen/zwave-smoke-tests/binaries"
    
    files_to_download = [
        "railtest_EFR32ZG28_brd4401c.hex",
        "railtest_ZGM230S_brd4205b.hex"
    ]
    
    for filename in files_to_download:
        url = f"{base_url}/{filename}"
        output_file = dist_bin / filename
        
        try:
            result = subprocess.run(
                ["curl", "-sf", url, "-o", str(output_file)],
                capture_output=True, text=True, check=True
            )
            if output_file.exists():
                downloaded_files.append(filename)
        except subprocess.CalledProcessError:
            pass
    
    if downloaded_files:
        log(f"Downloaded {len(downloaded_files)} railtest file(s)", "ok")
    else:
        log("Failed to download railtest binaries", "warn")
    
    return True

def create_manifest(dist_bin: Path, package_ref: str, branch: str | None, metadata_folder: Path | None = None) -> bool:
    """Create a manifest file describing where the binaries come from"""
    manifest = {
        "timestamp": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        "package_reference": package_ref,
        "branch": branch or "auto-detected",
        "sources": {}
    }
    
    # List files from Conan metadata
    conan_files = []
    if metadata_folder and metadata_folder.exists():
        for pattern in ["*.hex", "*v254.gbl", "*v255.gbl"]:
            for file in metadata_folder.glob(pattern):
                conan_files.append(file.name)
        
        if conan_files:
            manifest["sources"]["conan_metadata"] = {
                "metadata_folder": str(metadata_folder),
                "files": sorted(conan_files)
            }
    
    # List railtest files from Artifactory
    railtest_files = []
    railtest_base_url = "https://artifactory.silabs.net/artifactory/zwave-gen/zwave-smoke-tests/binaries"
    railtest_files_list = [
        "railtest_EFR32ZG28_brd4401c.hex",
        "railtest_ZGM230S_brd4205b.hex"
    ]
    
    for filename in railtest_files_list:
        if (dist_bin / filename).exists():
            railtest_files.append(filename)
    
    if railtest_files:
        manifest["sources"]["artifactory"] = {
            "base_url": railtest_base_url,
            "files": sorted(railtest_files)
        }
    
    # List all files in dist_bin
    all_files = []
    if dist_bin.exists():
        for file in dist_bin.iterdir():
            if file.is_file():
                # Calculate SHA256 checksum
                sha256_hash = hashlib.sha256()
                try:
                    with file.open("rb") as f:
                        for chunk in iter(lambda: f.read(4096), b""):
                            sha256_hash.update(chunk)
                    checksum = sha256_hash.hexdigest()
                except Exception as e:
                    log(f"Failed to calculate checksum for {file.name}: {e}", "warn")
                    checksum = None
                
                all_files.append({
                    "name": file.name,
                    "size": file.stat().st_size,
                    "sha256": checksum,
                    "modified": datetime.fromtimestamp(file.stat().st_mtime, tz=timezone.utc).isoformat().replace('+00:00', 'Z')
                })
    
    manifest["files"] = sorted(all_files, key=lambda x: x["name"])
    
    # Write manifest file
    manifest_file = dist_bin / "manifest.json"
    try:
        with manifest_file.open('w') as f:
            json.dump(manifest, f, indent=2)
        log(f"Created manifest: {manifest_file}", "ok")
        return True
    except Exception as e:
        log(f"Failed to create manifest: {e}", "warn")
        return False

def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        description="Fetch build artifacts from Conan and Artifactory",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          # Use default branch detection (main or current git branch)
  %(prog)s --branch develop         # Use 'develop' branch artifacts
  %(prog)s --branch feature/my-feat # Use 'feature/my-feat' branch artifacts
        """
    )
    parser.add_argument(
        "--branch",
        type=str,
        default=None,
        help="Branch name to use for fetching artifacts (will be sanitized like in Jenkinsfile). Default: auto-detect from git or use 'main'"
    )
    
    args = parser.parse_args()
    
    print(f"\n{Colors.CYAN}Fetching Build Artifacts{Colors.NC}\n{'='*38}\n")
    
    # Get workspace directory
    script_dir = Path(__file__).parent
    workspace_dir = script_dir.parent.parent
    z_wave_dir = workspace_dir / "z-wave"
    
    os.chdir(workspace_dir)
    
    # Check prerequisites
    if not check_slt():
        sys.exit(1)
    
    # Check Conan is available (should be installed via setup_tools.py)
    if not check_conan():
        sys.exit(1)
    
    # Configure Conan remotes from remotes.json
    success, remote_name = configure_conan_remotes(workspace_dir)
    if not success:
        sys.exit(1)
    
    # Build package reference
    log("Determining Conan package reference...", "info")
    if args.branch:
        log(f"Using specified branch: {args.branch}", "info")
    package_ref = build_conan_ref(workspace_dir, z_wave_dir, args.branch)
    log(f"Package reference: {package_ref}", "ok")
    
    # Download metadata
    if not download_conan_metadata(package_ref, remote_name):
        sys.exit(1)
    
    # Get metadata folder
    metadata_folder = get_metadata_folder(package_ref)
    if not metadata_folder:
        log("Could not determine metadata folder", "fail")
        sys.exit(1)
    
    log(f"Metadata folder: {metadata_folder}", "info")
    
    # Clean dist/bin directory before downloading
    dist_bin = workspace_dir / "dist" / "bin"
    if not clean_dist_bin(dist_bin):
        sys.exit(1)
    
    # Copy binaries
    if not copy_binaries(metadata_folder, dist_bin):
        sys.exit(1)
    
    # Download railtest binaries (no authentication required)
    download_railtest_binaries(dist_bin)
    
    # Create manifest file describing where binaries come from
    create_manifest(dist_bin, package_ref, args.branch, metadata_folder)
    
    print()
    log("Build artifacts fetched successfully!", "ok")
    log(f"Binaries are available in: {dist_bin}", "info")

if __name__ == "__main__":
    main()

# DevContainer Setup for z-wave-ts-silabs

This devcontainer provides a complete development environment for the z-wave-ts-silabs project, allowing you to debug and run hardware tests on the stdv2-1 setup.

## Prerequisites

Before using this devcontainer, ensure you have:

1. **SLT installed on the host machine**
   - SLT should be installed at `~/.local/bin/slt`
   - The configuration file `~/.local/bin/slt_default.ini` should also exist
   - SLT cache directory will be created at `~/.zw_devcontainer_slt_cache`

2. **SSH keys configured**
   - Your SSH keys should be available at `~/.ssh` for git access

3. **Git submodule for test catalog**
   - The test catalog is provided via a git submodule with sparse checkout
   - Initialize with: `git submodule update --init --recursive`

## Features

- **Commander CLI**: Installed via SLT during container creation
- **Conan**: Installed via SLT during container creation (for build artifacts retrieval)
- **Python 3.12+**: Pre-installed with pip configured
- **Test Catalog**: Git submodule with sparse checkout (only test/ directory)
- **Build Artifacts**: Automatically fetched from Conan and Artifactory on container startup
- **VSCode Extensions**: Python, Pytest, and debugging tools pre-configured

**Note**: Commander and Conan are both installed by the same setup script (`setup_tools.py`) during container creation.

## Usage

### Opening the DevContainer

1. Open the project in VSCode/Cursor
2. When prompted, click "Reopen in Container" or use Command Palette (`Ctrl+Shift+P`) → "Dev Containers: Reopen in Container"

### Running Tests

Once the container is ready, you can run tests with:

```bash
pytest --hw-cluster stdv2-1 test/
```

Or from the examples directory:

```bash
cd examples
pytest --hw-cluster stdv2-1 ../test/
```

### VSCode Tasks

Tasks are available via `Ctrl+Shift+P` → "Tasks: Run Task":

1. **Update Build Artifacts**: Fetches the latest build artifacts (binaries) from Conan and Artifactory

To update the test catalog submodule, use: `git submodule update --remote test`

## Configuration

### Commander CLI Path

The `examples/config.json` file is configured to use the Linux path for commander-cli:
- Linux: `/opt/silabs/commander-cli/commander-cli`

### Clusters Configuration

The `examples/clusters.json` file includes the `stdv2-1` cluster configuration for hardware testing.

### Build Artifacts Configuration

Build artifacts are automatically fetched on container startup. The script retrieves:
- Z-Wave firmware binaries (`.hex`, `.gbl` files) from Conan
- Railtest binaries from Artifactory (no authentication required)

**Package Version Override**:

You can override the package version/channel/revision via environment variables:
- `PACKAGE_VERSION`: Override package version (e.g., `1.2.3`)
- `PACKAGE_CHANNEL`: Override package channel (e.g., `main`, `develop`)
- `RECIPE_REVISION`: Override recipe revision (git commit hash)

The default version is read from `conanfile.py` at the project root.

## Troubleshooting

### SLT not found

If SLT is not found, ensure it's installed on the host and the mount paths are correct in `devcontainer.json`.

### Test catalog not available

If the test catalog is not available:
1. Initialize the git submodule: `git submodule update --init --recursive`
2. The submodule uses sparse checkout to only fetch the test/ directory

### Network access to WPKs

The container needs network access to resolve WPK hostnames (`jlink{serial}.silabs.com`). Ensure your network configuration allows this.

### Cursor Extension Marketplace Access

If you're using Cursor IDE and cannot access the extension marketplace due to corporate SSL inspection:

1. **Run the SSL configuration script on the host:**
   ```bash
   bash .devcontainer/scripts/configure_cursor_ssl.sh
   ```

2. **Add the environment variables to your shell profile** (as instructed by the script)

3. **Restart Cursor** or launch it with the environment variables loaded

The script configures Cursor to use the corporate root certificate (`/usr/share/ca-certificates/pkicorp/sl-root-ca.crt`) which is required when your corporate gateway decrypts SSL connections.

**Alternative:** If the marketplace still doesn't work, you can install extensions manually:
- Download the `.vsix` file from OpenVSX marketplace
- Install via: `cursor --install-extension <path-to-vsix-file>`

## File Structure

```
.devcontainer/
├── Dockerfile                 # Container image definition
├── devcontainer.json          # DevContainer configuration
├── README.md                  # This file
└── scripts/
    ├── initialize.sh          # Initial setup script
    ├── setup_tools.py        # Commander CLI and Conan installation
    ├── setup_zwave_repo.py    # Z-Wave repository setup
    ├── setup_test_environment.py  # Test environment setup
    └── fetch_build_artifacts.py   # Build artifacts retrieval
```

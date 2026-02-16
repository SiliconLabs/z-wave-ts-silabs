"""
Root conftest.py for the z-wave-ts-silabs project.
This ensures that modules installed via pip install --user are available to pytest.
"""
import sys
import site
from pathlib import Path

# Add user site-packages to Python path if not already present
# This is needed because modules are installed with --user flag
user_site = site.getusersitepackages()
if user_site and user_site not in sys.path:
    sys.path.insert(0, user_site)

# Also add the z-wave-test-system directory to path if it exists
# This allows importing modules directly from the source if not installed
z_wave_test_system = Path(__file__).parent / "z-wave-test-system"
if z_wave_test_system.exists():
    # Add z_wave_ts to path
    z_wave_ts_path = z_wave_test_system / "z_wave_ts"
    if z_wave_ts_path.exists() and str(z_wave_ts_path) not in sys.path:
        sys.path.insert(0, str(z_wave_ts_path))
    
    # Add z_wave to path
    z_wave_path = z_wave_test_system / "z_wave"
    if z_wave_path.exists() and str(z_wave_path) not in sys.path:
        sys.path.insert(0, str(z_wave_path))

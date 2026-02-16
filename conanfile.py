from conan import ConanFile

class ZWaveSampleAppInternal(ConanFile):
    name = "zwave_sample_app_internal"
    version = "1.0.0"
    # This file is used to determine the package version when retrieving build artifacts
    # The version can be overridden via the PACKAGE_VERSION environment variable

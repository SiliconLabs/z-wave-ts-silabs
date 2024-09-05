#!/bin/env bash

# usage: ./run_tests.sh <test_scripts>

# enable bash debug output
set -x

# run the tests (just remove .venv/bin if not running in a venv)
.venv/bin/pytest --show-capture=log --durations=0 --junit-xml=logs/junit-results.xml "$1"

# move pytest log files to the log folder of the most recent test run
logdir=$(ls -td logs/*/ | head -n 1)
mv logs/pytest.log "$logdir"
mv logs/junit-results.xml "$logdir"

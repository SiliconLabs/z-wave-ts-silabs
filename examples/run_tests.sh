#!/usr/bin/env bash

if [ "$#" -ne 2 ]; then
    echo "usage: $0 <cluster> <test_scripts>"
    exit 1
fi

# enable bash debug output
set -x

# run the tests (just remove .venv/bin if not running in a venv)
pytest --show-capture=log --durations=0 --junit-xml=logs/junit-results.xml --reruns 2 --reruns-delay 1 --hw-cluster "$1" "$2"

# move pytest log files to the log folder of the most recent test run
logdir=$(ls -td logs/*/ | head -n 1)
mv logs/pytest.log "$logdir"
mv logs/junit-results.xml "$logdir"

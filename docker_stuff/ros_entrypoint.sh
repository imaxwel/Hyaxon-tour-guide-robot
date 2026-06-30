#!/usr/bin/env bash
set -eo pipefail

source /opt/ros/jazzy/setup.bash

if [ -f /ws/install/setup.bash ]; then
  source /ws/install/setup.bash
fi

set -u
exec "$@"

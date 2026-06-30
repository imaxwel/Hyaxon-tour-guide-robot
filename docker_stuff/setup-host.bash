#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

VIDEO_GID="$(getent group video | awk -F: '{print $3}')"
RENDER_GID="$(getent group render | awk -F: '{print $3}')"

VIDEO_GID="${VIDEO_GID:-44}"
RENDER_GID="${RENDER_GID:-110}"
DISPLAY_VALUE="${DISPLAY:-:0}"
DEFAULT_PROXY="${TOURBOT_PROXY:-http://192.168.100.8:34601}"
DEFAULT_NO_PROXY="${NO_PROXY:-localhost,127.0.0.1,::1,192.168.0.0/16,10.0.0.0/8,172.16.0.0/12}"

cat > "${SCRIPT_DIR}/.env" <<EOF
USERNAME=$(id -un)
UID=$(id -u)
GID=$(id -g)
DISPLAY=${DISPLAY_VALUE}
VIDEO_GID=${VIDEO_GID}
RENDER_GID=${RENDER_GID}
ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-42}
RMW_IMPLEMENTATION=${RMW_IMPLEMENTATION:-rmw_fastrtps_cpp}
LIBGL_ALWAYS_SOFTWARE=${LIBGL_ALWAYS_SOFTWARE:-1}
MESA_LOADER_DRIVER_OVERRIDE=${MESA_LOADER_DRIVER_OVERRIDE:-llvmpipe}
HTTP_PROXY=${HTTP_PROXY:-${DEFAULT_PROXY}}
HTTPS_PROXY=${HTTPS_PROXY:-${DEFAULT_PROXY}}
NO_PROXY=${DEFAULT_NO_PROXY}
http_proxy=${http_proxy:-${DEFAULT_PROXY}}
https_proxy=${https_proxy:-${DEFAULT_PROXY}}
no_proxy=${no_proxy:-${DEFAULT_NO_PROXY}}
EOF

touch "${SCRIPT_DIR}/.xauth"
if command -v xauth >/dev/null 2>&1; then
  xauth nlist "${DISPLAY_VALUE}" 2>/dev/null | sed -e 's/^..../ffff/' | xauth -f "${SCRIPT_DIR}/.xauth" nmerge - 2>/dev/null || true
fi
chmod 600 "${SCRIPT_DIR}/.xauth"

echo "Wrote ${SCRIPT_DIR}/.env"
echo "Wrote ${SCRIPT_DIR}/.xauth"

if [ ! -d /dev/dri ]; then
  echo "Warning: /dev/dri is missing; Gazebo/RViz may fall back to slow software rendering." >&2
fi

if ! xauth -f "${SCRIPT_DIR}/.xauth" list >/dev/null 2>&1 || [ ! -s "${SCRIPT_DIR}/.xauth" ]; then
  echo "Warning: Xauthority export is empty. If GUI cannot open, run:" >&2
  echo "  xhost +SI:localuser:$(id -un)" >&2
fi

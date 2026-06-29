#!/usr/bin/env bash
set -e

if [ -n "${XDG_RUNTIME_DIR:-}" ]; then
  mkdir -p "${XDG_RUNTIME_DIR}"
  chmod 700 "${XDG_RUNTIME_DIR}" || true
fi

source /opt/ros/jazzy/setup.bash

# CycloneDDS: ensure ParticipantIndex=none so large launches do not exhaust participant indices
_CDDS_XML="${HOME}/.cyclonedds.xml"
if [ ! -f "${_CDDS_XML}" ]; then
  cat > "${_CDDS_XML}" <<CDDS
<CycloneDDS xmlns="https://cdds.io/config">
  <Domain Id="any">
    <Discovery>
      <ParticipantIndex>none</ParticipantIndex>
    </Discovery>
  </Domain>
</CycloneDDS>
CDDS
fi
export CYCLONEDDS_URI="file://${_CDDS_XML}"

if [ -f /workspace/install/setup.bash ]; then
  source /workspace/install/setup.bash
fi

exec "$@"


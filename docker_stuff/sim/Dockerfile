ARG BASE_IMAGE=osrf/ros:jazzy-desktop-full
FROM ${BASE_IMAGE}

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ENV DEBIAN_FRONTEND=noninteractive
ENV ROS_DISTRO=jazzy

ARG USERNAME=ros
ARG UID=1000
ARG GID=1000
ARG HTTP_PROXY=
ARG HTTPS_PROXY=
ARG NO_PROXY=localhost,127.0.0.1,::1
ARG http_proxy=
ARG https_proxy=
ARG no_proxy=localhost,127.0.0.1,::1

ENV CYCLONEDDS_URI=file:///home/${USERNAME}/.cyclonedds.xml

ENV HTTP_PROXY=${HTTP_PROXY}
ENV HTTPS_PROXY=${HTTPS_PROXY}
ENV NO_PROXY=${NO_PROXY}
ENV http_proxy=${http_proxy}
ENV https_proxy=${https_proxy}
ENV no_proxy=${no_proxy}

RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
    bash-completion \
    build-essential \
    ca-certificates \
    cmake \
    curl \
    git \
    gnupg \
    libeigen3-dev \
    libgl1-mesa-dri \
    libglx-mesa0 \
    libglib2.0-0 \
    libglu1-mesa \
    libxkbcommon-x11-0 \
    lsb-release \
    mesa-utils \
    pkg-config \
    python3-colcon-common-extensions \
    python3-dev \
    python3-numpy \
    python3-pip \
    python3-rosdep \
    python3-vcstool \
    python3-yaml \
    sudo \
    x11-apps \
    xauth \
    ros-jazzy-apriltag-ros \
    ros-jazzy-camera-ros \
    ros-jazzy-cv-bridge \
    ros-jazzy-image-proc \
    ros-jazzy-image-transport \
    ros-jazzy-image-transport-plugins \
    ros-jazzy-image-view \
    ros-jazzy-irobot-create-nodes \
    ros-jazzy-nav2-bringup \
    ros-jazzy-rmw-cyclonedds-cpp \
    ros-jazzy-rqt-image-view \
    ros-jazzy-slam-toolbox \
    ros-jazzy-tf2-tools \
    ros-jazzy-turtlebot4-simulator \
    ros-jazzy-diagnostic-updater \
    && rm -rf /var/lib/apt/lists/*

RUN if ! getent group "${GID}" >/dev/null; then groupadd --gid "${GID}" "${USERNAME}"; fi \
    && if ! id -u "${USERNAME}" >/dev/null 2>&1; then \
         if getent passwd "${UID}" >/dev/null; then \
           EXISTING_USER="$(getent passwd "${UID}" | cut -d: -f1)" \
           && usermod --login "${USERNAME}" "${EXISTING_USER}" \
           && usermod --home "/home/${USERNAME}" --move-home "${USERNAME}"; \
         else \
           useradd --uid "${UID}" --gid "${GID}" -m "${USERNAME}"; \
         fi; \
       fi \
    && usermod --uid "${UID}" --gid "${GID}" "${USERNAME}" \
    && usermod -aG sudo,video "${USERNAME}" \
    && if getent group render >/dev/null; then usermod -aG render "${USERNAME}"; fi \
    && echo "${USERNAME} ALL=(ALL) NOPASSWD:ALL" > "/etc/sudoers.d/${USERNAME}" \
    && chmod 0440 "/etc/sudoers.d/${USERNAME}" \
    && mkdir -p "/home/${USERNAME}/.ros" "/home/${USERNAME}/.gz" "/tmp/runtime-${USERNAME}" \
    && printf '%s\n' \
         'source /opt/ros/jazzy/setup.bash' \
         'export CYCLONEDDS_URI="${CYCLONEDDS_URI:-file://${HOME}/.cyclonedds.xml}"' \
         '[ -f /workspace/install/setup.bash ] && source /workspace/install/setup.bash' \
         >> "/home/${USERNAME}/.bashrc" \
    && printf '%s\n' \
         'source /opt/ros/jazzy/setup.bash' \
         'export CYCLONEDDS_URI="${CYCLONEDDS_URI:-file://${HOME}/.cyclonedds.xml}"' \
         '[ -f /workspace/install/setup.bash ] && source /workspace/install/setup.bash' \
         > "/home/${USERNAME}/.bash_profile" \
    && chown -R "${UID}:${GID}" "/home/${USERNAME}" "/tmp/runtime-${USERNAME}"

RUN rosdep init || true

COPY docker_stuff/sim/entrypoint.bash /usr/local/bin/tourbot-entrypoint
RUN chmod +x /usr/local/bin/tourbot-entrypoint

USER ${USERNAME}
WORKDIR /workspace

RUN rosdep update --rosdistro jazzy || true

ENTRYPOINT ["/usr/local/bin/tourbot-entrypoint"]
CMD ["bash"]

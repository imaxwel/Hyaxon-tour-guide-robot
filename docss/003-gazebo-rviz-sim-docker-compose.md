# Ubuntu 22.04 上用 Docker Compose 构建和运行 Gazebo + RViz 仿真

## 1. 结论

当前宿主机如果是 Ubuntu 22.04，最佳实践不是在宿主机上强行安装 ROS 2 Jazzy，而是：

- 宿主机只安装 Docker Engine、Docker Compose plugin、显卡驱动和必要的 GUI 转发工具。
- 容器内使用 Ubuntu 24.04 Noble + ROS 2 Jazzy + Gazebo Harmonic + TurtleBot4 simulator。
- 通过 Docker Compose 固化构建、GUI、GPU、网络、volume 和启动命令。

原因：

- 当前项目 README 声明目标环境是 ROS 2 Jazzy + Gazebo Harmonic。
- ROS 2 Jazzy 官方二进制包面向 Ubuntu 24.04 Noble。
- Ubuntu 22.04 Jammy 原生更适配 ROS 2 Humble，不适合直接作为 Jazzy/Gazebo Harmonic 的宿主运行环境。
- Docker 容器可以在 Ubuntu 22.04 宿主上运行 Ubuntu 24.04 用户态，避免在宿主机混装多个 ROS/Gazebo 版本。

当前仓库状态：

- 仓库已有 `docker_stuff/sim/Dockerfile` 和 `docker_stuff/compose.sim.yaml`，用于在 Ubuntu 22.04 宿主上运行 Ubuntu 24.04 + ROS 2 Jazzy + Gazebo Harmonic 仿真容器。
- 仓库已有 `src/tourbot_bringup/launch/sim.launch.py`，用于启动 TurtleBot4 Gazebo、spawn/bridge/RViz、AMCL localization 和 Nav2。
- 自定义 `cardboard_city` world 还不完整。
- `sim.launch.py` 当前已修正 custom world 默认值，指向仓库实际存在的 `worlds/cardboard_city/world.sdf` 的 stem：`worlds/cardboard_city/world`。
- `sim.launch.py` 当前会自动发布 AMCL 初始位姿，避免启动后一直等待 `map -> odom`。

推荐路线：

```text
Ubuntu 22.04 host
  -> Docker Engine + Compose plugin
  -> Ubuntu 24.04 / ROS Jazzy container
  -> Gazebo Harmonic + TurtleBot4 simulator + Nav2 + RViz
  -> bind mount 当前工程到 /workspace
```

## 2. 官方资料

建议以这些官方资料为准：

- Docker Engine on Ubuntu：<https://docs.docker.com/engine/install/ubuntu/>
- Docker Linux post-install：<https://docs.docker.com/engine/install/linux-postinstall/>
- Docker Compose GPU support：<https://docs.docker.com/compose/how-tos/gpu-support/>
- NVIDIA Container Toolkit：<https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html>
- ROS 2 Jazzy Ubuntu install：<https://docs.ros.org/en/jazzy/Installation/Ubuntu-Install-Debs.html>
- ROS 2 Docker networking how-to：<https://docs.ros.org/en/jazzy/How-To-Guides/Run-2-nodes-in-single-or-separate-docker-containers.html>
- TurtleBot4 simulator：<https://turtlebot.github.io/turtlebot4-user-manual/software/turtlebot4_simulator.html>
- TurtleBot4 simulation：<https://turtlebot.github.io/turtlebot4-user-manual/software/simulation.html>
- Gazebo ROS 2 launch：<https://gazebosim.org/docs/latest/ros2_launch_gazebo/>
- ROS 2 Jazzy + Gazebo Harmonic vendor packages：<https://gazebosim.org/docs/latest/ros2_gz_vendor_pkgs/>
- Nav2 Gazebo setup guide：<https://docs.nav2.org/setup_guides/gazebo.html>

## 3. 总体最佳实践

### 3.1 宿主机和容器职责分离

宿主机负责：

- Docker Engine
- Docker Compose plugin
- GPU 驱动
- X11/Wayland 显示服务
- `/dev/dri` 或 NVIDIA GPU device 访问
- 当前项目源码目录

容器负责：

- ROS 2 Jazzy
- Gazebo Harmonic
- RViz2
- TurtleBot4 simulator
- Nav2
- colcon build
- rosdep
- 仿真启动和调试命令

不要在宿主机同时 source Humble、Jazzy 或多个 Gazebo 发行版。宿主机可以完全不安装 ROS。

### 3.2 版本选择

推荐容器 base：

```text
Ubuntu 24.04 Noble
ROS 2 Jazzy
Gazebo Harmonic
TurtleBot4 Jazzy packages
```

示例 Dockerfile 使用：

```text
osrf/ros:jazzy-desktop-full
```

如果公司镜像仓库没有这个 tag，可以改用 `ubuntu:24.04`，然后按 ROS 2 Jazzy 官方 apt 流程安装 `ros-jazzy-desktop-full`。CI 中建议把 base image 固定到 digest，避免上游 tag 变更引入不可重复问题。

### 3.3 Compose 设计原则

推荐：

- 使用 Compose plugin，即 `docker compose`，不是老的 `docker-compose` Python 版本。
- Compose YAML 不写顶层 `version:`，遵循 Compose Specification。
- 使用非 root 用户运行容器，UID/GID 与宿主当前用户一致。
- 通过 bind mount 挂载源码，避免每次改代码都 rebuild image。
- build/install/log 写在宿主工作区，由 `.gitignore` 忽略，避免 root-owned 文件。
- GUI 使用 Xauthority 或受限 `xhost`，不要使用 `xhost +`。
- Intel/AMD 显卡映射 `/dev/dri`。
- NVIDIA 显卡使用 NVIDIA Container Toolkit 和 Compose GPU reservation。
- ROS 2 本机仿真优先使用 `network_mode: host`，减少 DDS 组播和端口映射问题。
- 设置 `ROS_DOMAIN_ID`，避免和同一局域网其他 ROS 2 系统互相发现。
- 不默认使用 `privileged: true`。只有明确知道缺哪个 device/capability 且无法细化授权时才临时使用。

## 4. 宿主机准备

以下步骤在 Ubuntu 22.04 宿主机执行。

### 4.1 安装 Docker Engine 和 Compose plugin

卸载可能存在的旧包：

```bash
for pkg in docker.io docker-doc docker-compose docker-compose-v2 podman-docker containerd runc; do
  sudo apt-get remove -y "$pkg" || true
done
```

安装 Docker 官方 apt 源：

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

允许当前用户非 root 使用 Docker：

```bash
sudo usermod -aG docker "$USER"
newgrp docker
```

验证：

```bash
docker version
docker compose version
docker run --rm hello-world
```

如果 `docker run hello-world` 仍提示 permission denied，重新登录桌面会话或重启机器。

### 4.2 安装 X11 辅助工具

```bash
sudo apt-get update
sudo apt-get install -y xauth x11-xserver-utils mesa-utils
```

确认当前桌面有 X11 display：

```bash
echo "$DISPLAY"
xauth list "$DISPLAY" || true
```

Ubuntu 22.04 默认可能是 Wayland 会话，但通常仍有 XWayland。Gazebo/RViz 用 X11 转发最简单。如果 `$DISPLAY` 为空，先切回图形桌面会话，或使用 VNC/noVNC 方案。

### 4.3 Intel/AMD GPU 检查

```bash
ls -ld /dev/dri
getent group video
getent group render || true
```

如果 `/dev/dri` 不存在，容器内 GUI 可能只能软件渲染，Gazebo/RViz 性能会很差。

### 4.4 NVIDIA GPU 检查

宿主机先确认驱动正常：

```bash
nvidia-smi
```

安装 NVIDIA Container Toolkit 后重启 Docker：

```bash
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
  sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

验证：

```bash
docker run --rm --gpus all nvidia/cuda:12.5.0-base-ubuntu22.04 nvidia-smi
```

如果 CUDA tag 在你的网络环境不可用，换成 NVIDIA 官方文档当前推荐的 tag。关键是验证 `--gpus all` 可以在容器里看到 GPU。

## 5. 推荐文件结构

建议在仓库根目录增加这些文件：

```text
.
├── docker_stuff/
│   ├── .env                     # 本机生成，不提交
│   ├── .xauth                   # 本机生成，不提交
│   ├── compose.sim.yaml
│   ├── setup-host.bash
│   └── sim/
│       ├── Dockerfile
│       └── entrypoint.bash
└── .dockerignore
```

建议把这些本机文件加入 `.gitignore`：

```text
docker_stuff/.env
docker_stuff/.xauth
```

当前仓库 `.gitignore` 已经忽略：

```text
build/
install/
log/
```

因此容器内 `colcon build` 产生的构建目录不会污染 Git 状态。

## 6. Dockerfile 推荐写法

路径：

```text
docker_stuff/sim/Dockerfile
```

推荐内容：

```dockerfile
# syntax=docker/dockerfile:1.7

ARG BASE_IMAGE=osrf/ros:jazzy-desktop-full
FROM ${BASE_IMAGE}

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ENV DEBIAN_FRONTEND=noninteractive
ENV ROS_DISTRO=jazzy

ARG USERNAME=ros
ARG UID=1000
ARG GID=1000

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash-completion \
    build-essential \
    ca-certificates \
    cmake \
    curl \
    git \
    gnupg \
    libeigen3-dev \
    libgl1-mesa-dri \
    libglib2.0-0 \
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
    ros-jazzy-camera-ros \
    ros-jazzy-cv-bridge \
    ros-jazzy-image-proc \
    ros-jazzy-image-transport \
    ros-jazzy-image-transport-plugins \
    ros-jazzy-image-view \
    ros-jazzy-irobot-create-nodes \
    ros-jazzy-nav2-bringup \
    ros-jazzy-rqt-image-view \
    ros-jazzy-slam-toolbox \
    ros-jazzy-tf2-tools \
    ros-jazzy-turtlebot4-simulator \
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
    && mkdir -p "/home/${USERNAME}/.ros" "/home/${USERNAME}/.gz" \
    && chown -R "${UID}:${GID}" "/home/${USERNAME}"

RUN rosdep init || true

COPY docker_stuff/sim/entrypoint.bash /usr/local/bin/tourbot-entrypoint
RUN chmod +x /usr/local/bin/tourbot-entrypoint

USER ${USERNAME}
WORKDIR /workspace

RUN rosdep update --rosdistro jazzy || true

ENTRYPOINT ["/usr/local/bin/tourbot-entrypoint"]
CMD ["bash"]
```

说明：

- `osrf/ros:jazzy-desktop-full` 用于减少 RViz/Gazebo GUI 依赖缺失概率。
- TurtleBot4 simulator、Nav2、SLAM Toolbox、image tools 明确安装在镜像里。
- 源码不 COPY 进镜像，而是运行时 bind mount 到 `/workspace`，适合开发和调试。
- 生产/CI 镜像可以另做一份 Dockerfile，把源码 COPY 进去并在 image build 阶段执行 `colcon build`。

## 7. Entrypoint 推荐写法

路径：

```text
docker_stuff/sim/entrypoint.bash
```

推荐内容：

```bash
#!/usr/bin/env bash
set -e

if [ -n "${XDG_RUNTIME_DIR:-}" ]; then
  mkdir -p "${XDG_RUNTIME_DIR}"
  chmod 700 "${XDG_RUNTIME_DIR}" || true
fi

source /opt/ros/jazzy/setup.bash

if [ -f /workspace/install/setup.bash ]; then
  source /workspace/install/setup.bash
fi

exec "$@"
```

注意：`docker compose exec sim bash -lc '...'` 启动的新 shell 不一定继承 entrypoint 里 source 后的 shell 状态。为了可重复，文档后面的命令仍会显式 `source /opt/ros/jazzy/setup.bash` 和 `source install/setup.bash`。

## 8. `.dockerignore` 推荐写法

路径：

```text
.dockerignore
```

推荐内容：

```text
.git
.venv
build
install
log
__pycache__
*.pyc
docker_stuff/.xauth
docker_stuff/.env
```

虽然开发镜像不 COPY 整个源码，Docker 仍会把 build context 发送给 Docker daemon。`.dockerignore` 可以避免 context 过大。

## 9. Compose 文件：Intel/AMD 或软件渲染

路径：

```text
docker_stuff/compose.sim.yaml
```

推荐内容：

```yaml
name: tourbot-sim

services:
  sim:
    build:
      context: ..
      dockerfile: docker_stuff/sim/Dockerfile
      args:
        USERNAME: ${USERNAME:-ros}
        UID: ${UID:-1000}
        GID: ${GID:-1000}
    image: tourbot-sim:jazzy-cpu
    container_name: tourbot-sim
    network_mode: host
    ipc: host
    shm_size: "2gb"
    working_dir: /workspace
    stdin_open: true
    tty: true
    environment:
      DISPLAY: ${DISPLAY}
      XAUTHORITY: /tmp/.docker.xauth
      QT_X11_NO_MITSHM: "1"
      XDG_RUNTIME_DIR: /tmp/runtime-${USERNAME:-ros}
      ROS_DOMAIN_ID: ${ROS_DOMAIN_ID:-42}
      RMW_IMPLEMENTATION: ${RMW_IMPLEMENTATION:-rmw_fastrtps_cpp}
      GZ_SIM_RESOURCE_PATH: /workspace/src/tourbot_bringup/worlds
    volumes:
      - ..:/workspace:rw
      - /tmp/.X11-unix:/tmp/.X11-unix:rw
      - ./.xauth:/tmp/.docker.xauth:ro
      - gz-cache:/home/${USERNAME:-ros}/.gz
      - ros-cache:/home/${USERNAME:-ros}/.ros
    devices:
      - /dev/dri:/dev/dri
    group_add:
      - "${VIDEO_GID:-44}"
      - "${RENDER_GID:-109}"
    command: sleep infinity

volumes:
  gz-cache:
  ros-cache:
```

说明：

- `network_mode: host` 是本机 ROS 2 仿真最省心的选择，DDS discovery、Gazebo/RViz 和多终端调试都更简单。
- `ipc: host` 能减少 Fast DDS shared memory、Gazebo 和 RViz 在容器里遇到的共享内存问题。安全要求严格的环境可以先去掉，只保留 `shm_size`，遇到问题再加回来。
- `QT_X11_NO_MITSHM=1` 可以规避部分 X11 shared memory 问题。
- `ROS_DOMAIN_ID=42` 只是示例。团队内应约定 domain id，避免串到别人的 ROS 2 系统。
- `/dev/dri` 用于 Intel/AMD Mesa/OpenGL。如果是纯 NVIDIA 主机，仍建议保留基础 Compose，再叠加 NVIDIA override。

## 10. Compose 文件：NVIDIA 可选覆盖

路径：

```text
docker_stuff/compose.nvidia.yaml
```

推荐内容：

```yaml
services:
  sim:
    environment:
      NVIDIA_VISIBLE_DEVICES: all
      NVIDIA_DRIVER_CAPABILITIES: graphics,utility,compute
      __GLX_VENDOR_LIBRARY_NAME: nvidia
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
```

启动 NVIDIA 模式时使用两个 Compose 文件：

```bash
docker compose --env-file docker_stuff/.env \
  -f docker_stuff/compose.sim.yaml \
  -f docker_stuff/compose.nvidia.yaml \
  up -d --build sim
```

混合显卡笔记本如果 Gazebo/RViz 没走独显，可临时增加：

```yaml
      __NV_PRIME_RENDER_OFFLOAD: "1"
      __VK_LAYER_NV_optimus: NVIDIA_only
```

是否需要这些变量取决于宿主机驱动和桌面会话，不建议默认写死。

## 11. 生成本机 `.env` 和 Xauthority

在仓库根目录执行：

```bash
cd /home/imax/4sim/gh-ref/tour-guide-robot/Hyaxon-tour-guide-robot
```

推荐直接使用仓库脚本：

```bash
chmod +x docker_stuff/setup-host.bash
./docker_stuff/setup-host.bash
```

脚本会生成：

```text
docker_stuff/.env
docker_stuff/.xauth
```

检查：

```bash
cat docker_stuff/.env
xauth -f docker_stuff/.xauth list
```

不要把 `docker_stuff/.env` 或 `docker_stuff/.xauth` 提交到 Git。它们是本机配置。

## 12. 配置 Xauthority

`docker_stuff/setup-host.bash` 已经会生成 `docker_stuff/.xauth`。推荐使用 Xauthority，而不是 `xhost +`。

如果输出为空，说明当前会话的 Xauthority 不容易导出。可以临时使用受限 `xhost`：

```bash
xhost +SI:localuser:"$(id -un)"
```

不要使用：

```bash
xhost +
```

结束仿真后撤销：

```bash
xhost -SI:localuser:"$(id -un)"
```

## 13. 构建镜像

Intel/AMD 或基础模式：

```bash
docker compose --env-file docker_stuff/.env -f docker_stuff/compose.sim.yaml build sim
```

NVIDIA 模式：

```bash
docker compose --env-file docker_stuff/.env \
  -f docker_stuff/compose.sim.yaml \
  -f docker_stuff/compose.nvidia.yaml \
  build sim
```

验证 Compose 展开后的配置：

```bash
docker compose --env-file docker_stuff/.env -f docker_stuff/compose.sim.yaml config
```

如果使用 NVIDIA：

```bash
docker compose --env-file docker_stuff/.env \
  -f docker_stuff/compose.sim.yaml \
  -f docker_stuff/compose.nvidia.yaml \
  config
```

## 14. 启动开发容器

Intel/AMD 或基础模式：

```bash
docker compose --env-file docker_stuff/.env -f docker_stuff/compose.sim.yaml up -d --build sim
```

NVIDIA 模式：

```bash
docker compose --env-file docker_stuff/.env \
  -f docker_stuff/compose.sim.yaml \
  -f docker_stuff/compose.nvidia.yaml \
  up -d --build sim
```

进入容器：

```bash
docker compose --env-file docker_stuff/.env -f docker_stuff/compose.sim.yaml exec sim bash
```

NVIDIA 模式进入容器也可以只用主 Compose 文件，因为容器已经创建完成：

```bash
docker compose --env-file docker_stuff/.env -f docker_stuff/compose.sim.yaml exec sim bash
```

确认基础环境：

```bash
echo "$ROS_DISTRO"
which ros2
ros2 --help
gz sim --version
```

确认 TurtleBot4 仿真包：

```bash
ros2 pkg prefix turtlebot4_gz_bringup
ros2 pkg prefix turtlebot4_navigation
ros2 pkg prefix turtlebot4_viz
```

确认 GUI/OpenGL：

```bash
xeyes
glxinfo -B
```

`xeyes` 能弹窗、`glxinfo -B` 能看到 renderer，说明 X11 和 OpenGL 基本可用。测试后关闭 `xeyes`。

NVIDIA 模式额外检查：

```bash
nvidia-smi
glxinfo -B | grep -E "OpenGL vendor|OpenGL renderer|OpenGL version"
```

如果 `nvidia-smi` 不存在，但 Gazebo/RViz 可以使用 OpenGL，也不一定是致命问题；关键看 NVIDIA Container Toolkit 是否正确挂载驱动库。

## 15. 在容器内构建当前工程

进入容器后：

```bash
cd /workspace
source /opt/ros/jazzy/setup.bash
```

更新 rosdep：

```bash
rosdep update --rosdistro jazzy
```

安装工程依赖：

```bash
rosdep install --from-paths src --ignore-src -r -y --rosdistro jazzy
```

注意：当前 `tourbot_bringup/package.xml` 没有完整声明 TurtleBot4/Gazebo/Nav2 运行依赖，所以 Dockerfile 已经显式安装了这些关键包。`rosdep install` 成功不代表仿真依赖全部来自 package.xml。

构建：

```bash
colcon build --packages-select tourbot_bringup --symlink-install
```

source 当前 workspace：

```bash
source install/setup.bash
```

确认工程包：

```bash
colcon list
ros2 pkg prefix tourbot_bringup
ros2 launch tourbot_bringup sim.launch.py --show-args
```

## 16. 运行默认 TurtleBot4 Gazebo + RViz 仿真

容器内执行：

```bash
cd /workspace
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 launch tourbot_bringup sim.launch.py
```

这个命令走 `use_custom_sim:=false`：

- Gazebo 使用 TurtleBot4 官方默认 world。
- 默认 TurtleBot4 model 是 `lite`，降低 Gazebo/RViz 资源压力。
- TurtleBot4 仿真机器人会被启动。
- Nav2 localization/navigation 会启动。
- RViz 会启动。
- 本工程会自动发布 `/initialpose`，避免 AMCL 一直等待初始位姿。

启动后检查：

```bash
ros2 topic list | grep -E "/clock|/tf|/odom|/scan|/map"
ros2 node list
ros2 lifecycle nodes
```

正常日志中应能看到：

```text
[tourbot_initial_pose_publisher]: Published initial pose x=0.000 y=0.000 yaw=0.000
[amcl]: initialPoseReceived
[lifecycle_manager_navigation]: Managed nodes are active
```

在 RViz 中：

1. Fixed Frame 设为 `map`。
2. 默认 launch 会自动设置初始 pose；如果地图或出生点不匹配，再用 `2D Pose Estimate` 手动修正。
3. 用 `Nav2 Goal` 发一个短距离目标。
4. 观察 Gazebo 中机器人是否运动，RViz 中 path/costmap 是否更新。

如果需要 OAK-D/RGBD 等 `standard` 模型传感器，显式传：

```bash
ros2 launch tourbot_bringup sim.launch.py model:=standard
```

## 17. 运行工程自带 custom world

当前可以直接运行：

```bash
ros2 launch tourbot_bringup sim.launch.py use_custom_sim:=true
```

当前 `sim.launch.py` 默认 custom world 指向仓库实际文件的 stem：

```text
src/tourbot_bringup/worlds/cardboard_city/world
```

TurtleBot4 Gazebo launch 会在内部追加 `.sdf`，因此这里传不带 `.sdf` 的路径。

如果要显式传入 world 和 map，可以这样运行：

```bash
cd /workspace
source /opt/ros/jazzy/setup.bash
source install/setup.bash

WORLD_STEM="$(ros2 pkg prefix --share tourbot_bringup)/worlds/cardboard_city/world"
MAP_YAML="$(ros2 pkg prefix --share tourbot_bringup)/maps/cardboard_city/map_area.yaml"

ros2 launch tourbot_bringup sim.launch.py \
  use_custom_sim:=true \
  custom_world:="$WORLD_STEM" \
  custom_map:="$MAP_YAML"
```

如果仍失败，先单独验证 SDF：

```bash
WORLD_SDF="$(ros2 pkg prefix --share tourbot_bringup)/worlds/cardboard_city/world.sdf"
ros2 launch ros_gz_sim gz_sim.launch.py gz_args:="$WORLD_SDF -r -v 4"
```

这只验证 Gazebo world，不会自动 spawn TurtleBot4，也不会启动 Nav2/RViz。

## 18. 运行 mission

mission 不是 Gazebo/RViz 的必要组成部分。只有在下面条件满足时再启动：

- Gazebo 中已有 TurtleBot4。
- Nav2 lifecycle nodes 已 active。
- RViz 能看到 map、robot、TF、costmap。
- camera topic 存在：
  - `/oakd/rgb/preview/image_raw`
  - `/oakd/rgb/preview/camera_info`
- Gazebo world 里有与 landmarks 对应的 AprilTag。

第二个终端执行：

```bash
cd /home/imax/4sim/gh-ref/tour-guide-robot/Hyaxon-tour-guide-robot
docker compose --env-file docker_stuff/.env -f docker_stuff/compose.sim.yaml exec sim bash
```

容器内：

```bash
cd /workspace
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 launch tourbot_bringup mission.launch.py
```

当前自定义 world 没有完整 AprilTag 场景，所以 `mission.launch.py` 更适合作为节点集成测试入口，不代表完整导览仿真已经闭环。

## 19. Headless 模式建议

CI、远程服务器或没有桌面的机器不建议启动 RViz/Gazebo GUI。

当前 `tourbot_bringup/sim.launch.py` 已暴露 `rviz`、`nav2`、`slam`、`localization` 等参数。

轻量验证时建议先关闭 RViz：

```bash
cd /workspace
source /opt/ros/jazzy/setup.bash
source install/setup.bash

ros2 launch tourbot_bringup sim.launch.py rviz:=false
```

这仍会启动 Gazebo GUI。当前工程还没有独立 `headless:=true` 参数；真正只跑 Gazebo server 仍建议绕过本工程 launch 或继续扩展 launch 文件。

临时只跑 Gazebo server 可以绕过本工程 launch：

```bash
cd /workspace
source /opt/ros/jazzy/setup.bash
source install/setup.bash

WORLD_SDF="$(ros2 pkg prefix --share tourbot_bringup)/worlds/cardboard_city/world.sdf"
ros2 launch ros_gz_sim gz_server.launch.py world_sdf_file:="$WORLD_SDF"
```

如果只想验证 TurtleBot4 官方 launch 支持的参数，可以按实际 `--show-args` 结果运行；注意当前工程已经不再依赖官方顶层 wrapper 转发 Nav2 参数：

```bash
ros2 launch turtlebot4_gz_bringup turtlebot4_gz.launch.py \
  nav2:=true \
  slam:=false \
  localization:=true \
  rviz:=false
```

## 20. 常用 Compose 命令

查看容器状态：

```bash
docker compose --env-file docker_stuff/.env \
  -f docker_stuff/compose.sim.yaml \
  ps
```

进入容器：

```bash
docker compose --env-file docker_stuff/.env \
  -f docker_stuff/compose.sim.yaml \
  exec sim bash
```

启动或重建当前 sim 容器：

```bash
docker compose --env-file docker_stuff/.env \
  -f docker_stuff/compose.sim.yaml \
  up -d --force-recreate sim
```

看日志：

```bash
docker compose --env-file docker_stuff/.env \
  -f docker_stuff/compose.sim.yaml \
  logs --tail=120 sim
```

```bash
docker compose --env-file docker_stuff/.env -f docker_stuff/compose.sim.yaml logs -f sim
```

停止容器但保留 image 和 volume：

```bash
docker compose --env-file docker_stuff/.env -f docker_stuff/compose.sim.yaml stop sim
```

删除容器和默认网络，保留 named volumes：

```bash
docker compose --env-file docker_stuff/.env -f docker_stuff/compose.sim.yaml down
```

删除 Gazebo/ROS cache volumes：

```bash
docker compose --env-file docker_stuff/.env -f docker_stuff/compose.sim.yaml down -v
```

重建镜像：

```bash
docker compose --env-file docker_stuff/.env -f docker_stuff/compose.sim.yaml build --no-cache sim
```

清理 dangling image：

```bash
docker image prune
```

## 21. 验证清单

### 21.1 宿主机

```bash
docker compose version
echo "$DISPLAY"
ls -ld /tmp/.X11-unix
ls -ld /dev/dri || true
nvidia-smi || true
```

### 21.2 容器基础环境

```bash
echo "$ROS_DISTRO"
which ros2
gz sim --version
ros2 pkg prefix turtlebot4_gz_bringup
ros2 pkg prefix turtlebot4_navigation
ros2 pkg prefix turtlebot4_viz
```

### 21.3 GUI 和 GPU

```bash
xeyes
glxinfo -B
rviz2
```

`rviz2` 能打开但界面报 TF/map 错误是正常的，因为还没有启动机器人和 Nav2。这里主要验证 GUI 能显示。

### 21.4 ROS/Gazebo topic

仿真启动后：

```bash
ros2 topic echo --once /clock
ros2 topic list | grep -E "/tf|/tf_static|/odom|/scan|/map|/cmd_vel"
ros2 topic hz /scan
```

### 21.5 Nav2 lifecycle

```bash
ros2 lifecycle nodes
ros2 lifecycle get /bt_navigator
ros2 lifecycle get /controller_server
ros2 lifecycle get /planner_server
ros2 lifecycle get /amcl
```

### 21.6 TF

```bash
ros2 run tf2_tools view_frames
```

重点检查：

```text
map -> odom -> base_link -> sensors
```

## 22. 常见问题和处理

### 22.1 `Package 'turtlebot4_gz_bringup' not found`

容器内检查：

```bash
apt-cache policy ros-jazzy-turtlebot4-simulator
ros2 pkg prefix turtlebot4_gz_bringup
```

处理：

```bash
sudo apt-get update
sudo apt-get install -y ros-jazzy-turtlebot4-simulator ros-jazzy-irobot-create-nodes
```

如果 apt 找不到包，先确认容器确实是 Jazzy/Noble：

```bash
cat /etc/os-release
echo "$ROS_DISTRO"
```

### 22.2 `cannot open display`

宿主机检查：

```bash
echo "$DISPLAY"
xauth list "$DISPLAY" || true
ls -l docker_stuff/.xauth
```

重新生成 xauth：

```bash
./docker_stuff/setup-host.bash
```

重新创建容器：

```bash
docker compose --env-file docker_stuff/.env -f docker_stuff/compose.sim.yaml down
docker compose --env-file docker_stuff/.env -f docker_stuff/compose.sim.yaml up -d sim
```

仍失败时，临时使用受限 xhost：

```bash
xhost +SI:localuser:"$(id -un)"
```

### 22.3 RViz/Gazebo 打开但黑屏或软件渲染很慢

容器内检查：

```bash
glxinfo -B
ls -ld /dev/dri
groups
```

Intel/AMD：

- 确认 Compose 挂载了 `/dev/dri`。
- 确认 `group_add` 包含宿主 `video` 和 `render` 的 GID。
- 确认宿主当前用户能访问 `/dev/dri/renderD*`。

NVIDIA：

- 确认使用了 `docker_stuff/compose.nvidia.yaml`。
- 确认宿主 `nvidia-smi` 正常。
- 确认 Docker 的 `--gpus all` 验证通过。
- 检查 `NVIDIA_DRIVER_CAPABILITIES` 是否包含 `graphics`。

### 22.4 DDS 发现不到节点

本方案使用 `network_mode: host`，通常不会遇到 Docker bridge 网络导致的 ROS 2 discovery 问题。

仍有问题时检查：

```bash
echo "$ROS_DOMAIN_ID"
echo "$RMW_IMPLEMENTATION"
ros2 node list
```

确保所有终端、容器和宿主 ROS 工具使用相同 `ROS_DOMAIN_ID`。如果宿主机也装了 ROS，不要 source 不同发行版去连同一个 domain。

### 22.5 Gazebo 从 Fuel 下载模型很慢

工程的 `world.sdf` 使用了 Gazebo Fuel 的 Ground Plane：

```text
https://fuel.gazebosim.org/1.0/OpenRobotics/models/Ground Plane
```

首次启动会下载模型。Compose 中的 `gz-cache` volume 会缓存 `/home/<user>/.gz`，后续启动会快很多。

如果网络不可用，建议把必要模型 vendor 到工程内，并设置：

```text
GZ_SIM_RESOURCE_PATH=/workspace/src/tourbot_bringup/worlds:/workspace/models
```

### 22.6 custom world 路径

当前工程已经修正 `sim.launch.py` 默认 custom world 路径。

当前默认：

```text
worlds/cardboard_city/world
```

当前实际：

```text
worlds/cardboard_city/world.sdf
```

处理方式：

- 直接运行 `ros2 launch tourbot_bringup sim.launch.py use_custom_sim:=true`。
- 如需自定义路径，传不带 `.sdf` 后缀的 `custom_world` stem。

### 22.7 容器内生成 root-owned 文件

本方案通过 Dockerfile 创建与宿主 UID/GID 相同的用户，正常不会产生 root-owned `build/ install/ log/`。

如果已经产生 root-owned 文件，在宿主机修复：

```bash
sudo chown -R "$(id -u):$(id -g)" build install log
```

然后检查 Compose `.env`：

```bash
cat docker_stuff/.env
```

确保 `UID` 和 `GID` 是当前用户。

## 23. 安全建议

推荐：

- 不使用 `privileged: true`。
- 不挂载 `/var/run/docker.sock`。
- 不使用 `xhost +`。
- 不把 `docker_stuff/.env`、`docker_stuff/.xauth` 提交到 Git。
- 不在容器中存长期私钥或 token。
- 容器内以普通用户运行。
- GPU、X11、device 挂载只给仿真服务使用。
- CI/headless 环境禁用 RViz/Gazebo GUI。

可接受的开发便利：

- `network_mode: host`：本机 ROS 2 仿真调试很实用，但不适合多租户不可信环境。
- `ipc: host`：能减少 shared memory 问题，但安全边界比默认 IPC namespace 弱。安全要求高时先移除。

## 24. 团队落地建议

建议把 Docker 支持拆成两层：

### 24.1 开发镜像

用于本地开发：

- bind mount 源码
- 容器内 `colcon build --packages-select tourbot_bringup --symlink-install`
- 支持 Gazebo/RViz GUI
- 支持 GPU
- 可以 `docker compose exec` 多开终端调试

也就是本文的 Compose 方案。

### 24.2 CI/发布镜像

用于自动验证：

- COPY 源码进入 image
- 固定 base image digest
- 执行 `rosdep install`
- 执行 `colcon build`
- 运行 headless smoke test
- 不启动 RViz
- 不依赖 X11
- 不使用 `privileged`

CI 最小 smoke test 建议：

1. 启动 headless Gazebo。
2. 等待 `/clock`。
3. spawn robot。
4. 等待 `/tf`、`/odom`、`/scan`。
5. 等待 Nav2 lifecycle active。
6. 发一个短距离 Nav2 goal。
7. 断言 `/odom` 发生变化。

当前工程还需要先补齐 headless launch 参数，才能把这套 smoke test 做干净。

## 25. 最小命令汇总

宿主机一次性准备：

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl xauth x11-xserver-utils mesa-utils
docker compose version
```

生成本机 `.env` 和 Xauthority：

```bash
cd /home/imax/4sim/gh-ref/tour-guide-robot/Hyaxon-tour-guide-robot
chmod +x docker_stuff/setup-host.bash
./docker_stuff/setup-host.bash
```

启动容器：

```bash
docker compose --env-file docker_stuff/.env -f docker_stuff/compose.sim.yaml up -d --build sim
docker compose --env-file docker_stuff/.env -f docker_stuff/compose.sim.yaml exec sim bash
```

容器内构建工程：

```bash
cd /workspace
source /opt/ros/jazzy/setup.bash
rosdep update --rosdistro jazzy
rosdep install --from-paths src --ignore-src -r -y --rosdistro jazzy
colcon build --packages-select tourbot_bringup --symlink-install
source install/setup.bash
```

启动默认仿真：

```bash
ros2 launch tourbot_bringup sim.launch.py
```

启动 custom world：

```bash
WORLD_STEM="$(ros2 pkg prefix --share tourbot_bringup)/worlds/cardboard_city/world"
MAP_YAML="$(ros2 pkg prefix --share tourbot_bringup)/maps/cardboard_city/map_area.yaml"

ros2 launch tourbot_bringup sim.launch.py \
  use_custom_sim:=true \
  custom_world:="$WORLD_STEM" \
  custom_map:="$MAP_YAML"
```

停止：

```bash
docker compose --env-file docker_stuff/.env -f docker_stuff/compose.sim.yaml down
```

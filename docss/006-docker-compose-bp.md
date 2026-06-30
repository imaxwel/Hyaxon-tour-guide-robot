# Hyaxon Tour Guide Robot Docker Compose 最佳实践

> 编写日期：2026-06-30
> 目标主机：`xiao-5080` / `5080-MS-eSport-Z890M` / Ubuntu 24.04
> 目标目录：`/home/xiaozy/4sim/gh-ref/tour-guide-robot/Hyaxon-tour-guide-robot`
> 操作用户：`xiaozy`（已在 `docker`、`vglusers` 组）
> 图形桌面：TurboVNC `:22`，RFB `127.0.0.1:5922`，参考 `docss/102-xiaozy-turbovnc-bp.md`

---

## 1. 当前主机事实

以下信息来自 2026-06-30 在 `xiao-5080` 上的实际检查：

| 项目 | 当前值 | 影响 |
|---|---:|---|
| GPU | NVIDIA GeForce RTX 5080 | 可用于 RViz/Gazebo/图像处理/CUDA 工作负载 |
| 显存 | 16303 MiB | 单卡 16GB，仿真和大模型任务需避免同时抢占 |
| 驱动 | 580.126.20 | 新驱动，支持当前 RTX 5080 |
| CUDA runtime 上限 | 13.0 | 容器内 CUDA 12.x/13.x 用户态通常可由宿主驱动承载 |
| Docker | 29.3.1 | 可用 |
| Docker Compose | v5.1.1 | 可用，使用 `docker compose` 子命令 |
| Docker runtime | `nvidia` 已注册 | Compose 可通过 `gpus: all` 使用 GPU |
| xiaozy 组 | `users docker isaacusers vglusers` | 可无 sudo 运行容器；VirtualGL 用户权限已具备 |
| TurboVNC | `Xvnc :22` 正在运行 | GUI 容器应优先接入 `DISPLAY=:22` |
| 物理 Xorg | `:0` 正在运行 | VirtualGL 可用，但依赖 `xhost`/权限 |
| 当前 GPU 占用 | 约 9428 MiB，其中 `python` 约 9207 MiB | 启动 Gazebo/RViz 前应先确认剩余显存 |

结论：该主机已具备 Docker Compose + NVIDIA GPU + TurboVNC 图形栈的运行条件。当前主要风险不是环境缺失，而是 GPU 显存已经被其它 Python 进程大量占用，运行 Gazebo Harmonic、RViz2 或图像算法前必须先做资源检查。

---

## 2. 推荐目标

使用一个可复现的 ROS 2 Jazzy 开发镜像运行当前工程，源代码通过 bind mount 挂载，`install/`、`build/`、`log/` 使用命名 volume 或本地目录缓存，避免每次重建镜像都复制源码。

推荐目标分三层：

| 层级 | 目标 | 说明 |
|---|---|---|
| 基础镜像 | Ubuntu 24.04 + ROS 2 Jazzy + Nav2 + TurtleBot4 + Gazebo/RViz 依赖 | 固化系统依赖，减少裸机污染 |
| Compose 服务 | `dev`、`build`、`robot`、`mission`、`sim` | 同一镜像，不同启动命令/profile |
| 图形接入 | TurboVNC `DISPLAY=:22` + X11 socket | 通过 VNC 桌面运行 RViz/Gazebo GUI，远程稳定 |

不建议把该项目一开始拆成多个独立镜像。当前工程包较小，ROS 2 节点之间依赖同一个工作空间，过早拆分会增加接口、构建和调试成本。最佳实践是先用单镜像多服务，后续再按真实机器人/仿真/感知任务拆分。

---

## 3. 建议新增目录结构

在远端工程根目录创建以下文件：

```text
Hyaxon-tour-guide-robot/
├── docker_stuff/
│   ├── Dockerfile.jazzy
│   ├── ros_entrypoint.sh
│   ├── compose.yaml
│   └── .dockerignore
└── docss/
    └── 006-docker-compose-bp.md
```

本文档只规划步骤和推荐内容；真正落地时按第 7 节把容器相关文件全部写入远端工程的 `docker_stuff/` 目录。

---

## 4. 运行模式设计

### 4.1 `dev`：默认开发入口

用途：进入容器、安装/验证依赖、执行 `colcon build`、运行单条 ROS 命令。

特点：

- `network_mode: host`，ROS 2 DDS 与宿主/机器人网络直通。
- `ipc: host`，RViz/Gazebo/图像管线共享内存更稳定。
- `gpus: all`，让 NVIDIA Container Toolkit 注入 GPU。
- 挂载 `/tmp/.X11-unix` 和 `~/.Xauthority`，接入 VNC 的 X11。
- 工作目录固定为 `/ws`。
- 默认不自动 launch，避免容器起来就抢 GPU。

### 4.2 `build`：可重复编译入口

用途：执行 rosdep 和 `colcon build --symlink-install`，让所有人用同一条命令重建工作空间。

### 4.3 `robot`：真实 TurtleBot4 导航 bringup

运行：

```bash
ros2 launch tourbot_bringup robot.launch.py
```

该服务会启动 localization、Nav2、RViz2。适合真实机器人或已有底盘话题环境。

### 4.4 `mission`：任务/感知/行为 bringup

运行：

```bash
ros2 launch tourbot_bringup mission.launch.py
```

该服务依赖机器人底盘、里程计、相机话题和 `robot` 服务已经准备好。实际使用时通常先启动 `robot`，确认 Nav2 正常，再启动 `mission`。

### 4.5 `sim`：TurtleBot4 Gazebo 仿真

运行：

```bash
ros2 launch tourbot_bringup sim.launch.py
```

当前 README 已说明自定义 cardboard city Gazebo 世界尚未完全完成，因此 `sim` 应作为仿真验证入口，而不是等价于真实场景的最终验收。

---

## 5. 前置检查

所有命令都在 `xiao-5080` 上执行，不在 Dell notebook 上执行。

```bash
ssh xiao-5080
cd /home/xiaozy/4sim/gh-ref/tour-guide-robot/Hyaxon-tour-guide-robot
```

检查 Docker/GPU：

```bash
docker --version
docker compose version
docker info --format '{{json .Runtimes}}' | grep -o 'nvidia'
nvidia-smi
```

检查 VNC/X11：

```bash
pgrep -af 'Xvnc.*:22'
ss -tlnp 'sport = :5922'
ls -l /tmp/.X11-unix/X22
```

如果 VNC 未运行：

```bash
~/scripts/start-turbovnc-vnc22.sh
```

客户端建立 tunnel 并连接桌面：

```bash
ssh -N -L 5922:127.0.0.1:5922 xiao-5080
/opt/TurboVNC/bin/vncviewer localhost::5922
```

资源门槛建议：

```bash
nvidia-smi --query-gpu=memory.used,memory.free,utilization.gpu --format=csv
```

- 只运行 ROS 节点和 RViz：建议空闲显存至少 2-3GB。
- 运行 Gazebo Harmonic + RViz：建议空闲显存至少 5-6GB。
- 当前已观测到一个 Python 进程占用约 9.2GB，若 Gazebo/RViz 异常、卡顿或 OOM，先协调停止该进程。

---

## 6. 代理基线

当前主机的 `docker pull` 已经回走代理。容器内仍需要显式配置代理，覆盖以下四类流量：

| 类型 | 配置位置 | 目标 |
|---|---|---|
| `apt` | `/etc/apt/apt.conf.d/99proxy` | `apt update/install` 走代理 |
| `pip` | `/etc/pip.conf` | `pip install` 走代理 |
| Git/GitHub | `/etc/gitconfig` + `HTTP(S)_PROXY` | `git clone/fetch`、GitHub HTTPS 走代理 |
| 容器内 Docker CLI | `/root/.docker/config.json` + `DOCKER_CONFIG` | 容器内执行 `docker build/run` 时向子容器/构建注入代理 |

统一代理地址：

```bash
TOURBOT_PROXY=http://192.168.100.8:31415
TOURBOT_NO_PROXY=localhost,127.0.0.1,::1,192.168.0.0/16,10.0.0.0/8,172.16.0.0/12,xiao-5080,5080-MS-eSport-Z890M
```

原则：

- Docker daemon 的 `pull` 代理继续由宿主机配置负责，Compose 文档不重复配置宿主 daemon。
- 镜像构建阶段使用 `ARG` + `ENV`，让 `apt`、`pip`、`git` 在 build 时可用。
- 容器运行阶段保留 `HTTP_PROXY`、`HTTPS_PROXY`、`NO_PROXY`，让交互式调试时的 `apt/pip/git` 同样可用。
- `NO_PROXY` 必须覆盖 localhost、局域网、ROS 2 机器人网络和主机名，避免 DDS、TurtleBot4、VNC、Docker socket 等内网流量被错误转发到代理。
- 不建议在仓库中提交包含账号密码的代理 URL；当前代理无凭据，可直接写入文档和 Compose。

---

## 7. 落地文件

### 7.1 `docker_stuff/.dockerignore`

```dockerignore
.git
build
install
log
.cache
.vscode
.idea
*.bag
*.db3
*.mcap
*.pyc
__pycache__
```

### 7.2 `docker_stuff/ros_entrypoint.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

source /opt/ros/jazzy/setup.bash

if [ -f /ws/install/setup.bash ]; then
  source /ws/install/setup.bash
fi

exec "$@"
```

### 7.3 `docker_stuff/Dockerfile.jazzy`

```dockerfile
FROM osrf/ros:jazzy-desktop-full

ARG TOURBOT_PROXY=http://192.168.100.8:31415
ARG TOURBOT_NO_PROXY=localhost,127.0.0.1,::1,192.168.0.0/16,10.0.0.0/8,172.16.0.0/12,xiao-5080,5080-MS-eSport-Z890M

ENV DEBIAN_FRONTEND=noninteractive
ENV ROS_DISTRO=jazzy
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
ENV QT_X11_NO_MITSHM=1
ENV NVIDIA_VISIBLE_DEVICES=all
ENV NVIDIA_DRIVER_CAPABILITIES=compute,utility,graphics,display
ENV HTTP_PROXY=${TOURBOT_PROXY}
ENV HTTPS_PROXY=${TOURBOT_PROXY}
ENV ALL_PROXY=${TOURBOT_PROXY}
ENV NO_PROXY=${TOURBOT_NO_PROXY}
ENV http_proxy=${TOURBOT_PROXY}
ENV https_proxy=${TOURBOT_PROXY}
ENV all_proxy=${TOURBOT_PROXY}
ENV no_proxy=${TOURBOT_NO_PROXY}
ENV PIP_CONFIG_FILE=/etc/pip.conf
ENV DOCKER_CONFIG=/root/.docker

SHELL ["/bin/bash", "-c"]

RUN set -eux; \
    printf 'Acquire::http::Proxy "%s";\nAcquire::https::Proxy "%s";\n' "${TOURBOT_PROXY}" "${TOURBOT_PROXY}" > /etc/apt/apt.conf.d/99proxy; \
    printf '[global]\nproxy = %s\ntimeout = 120\n' "${TOURBOT_PROXY}" > /etc/pip.conf; \
    printf '[http]\n	proxy = %s\n[https]\n	proxy = %s\n' "${TOURBOT_PROXY}" "${TOURBOT_PROXY}" > /etc/gitconfig; \
    mkdir -p /root/.docker; \
    printf '{"proxies":{"default":{"httpProxy":"%s","httpsProxy":"%s","noProxy":"%s"}}}\n' "${TOURBOT_PROXY}" "${TOURBOT_PROXY}" "${TOURBOT_NO_PROXY}" > /root/.docker/config.json

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash-completion \
    build-essential \
    cmake \
    git \
    python3-colcon-common-extensions \
    python3-pip \
    python3-rosdep \
    python3-vcstool \
    python3-yaml \
    libgl1 \
    libglvnd0 \
    libglx0 \
    libegl1 \
    libx11-6 \
    libxext6 \
    libxrender1 \
    libxcb1 \
    libxcb-xinerama0 \
    mesa-utils \
    x11-apps \
    v4l-utils \
    docker.io \
    ros-${ROS_DISTRO}-nav2-bringup \
    ros-${ROS_DISTRO}-navigation2 \
    ros-${ROS_DISTRO}-slam-toolbox \
    ros-${ROS_DISTRO}-rviz2 \
    ros-${ROS_DISTRO}-image-transport \
    ros-${ROS_DISTRO}-image-transport-plugins \
    ros-${ROS_DISTRO}-image-proc \
    ros-${ROS_DISTRO}-image-view \
    ros-${ROS_DISTRO}-cv-bridge \
    ros-${ROS_DISTRO}-tf2-ros \
    ros-${ROS_DISTRO}-camera-ros \
    ros-${ROS_DISTRO}-turtlebot4-desktop \
    ros-${ROS_DISTRO}-turtlebot4-navigation \
    ros-${ROS_DISTRO}-turtlebot4-viz \
    ros-${ROS_DISTRO}-turtlebot4-simulator \
    && rm -rf /var/lib/apt/lists/*

RUN rosdep init 2>/dev/null || true

COPY ros_entrypoint.sh /ros_entrypoint.sh
RUN chmod +x /ros_entrypoint.sh

WORKDIR /ws
ENTRYPOINT ["/ros_entrypoint.sh"]
CMD ["bash"]
```

说明：

- 使用 `osrf/ros:jazzy-desktop-full` 是为了优先保证 RViz/Gazebo/X11 依赖完整，减少首轮调试成本。
- 若镜像体积成为问题，再切到 `ros:jazzy-ros-base` 并显式补 GUI 包。
- `rosdep init` 在镜像构建阶段允许失败，避免基础镜像已有 rosdep 配置时报错。
- TurtleBot4 包名如果因 apt 源差异安装失败，先用 `apt-cache search ros-jazzy-turtlebot4` 在容器基础层确认具体包名，再调整 Dockerfile。

### 7.4 `docker_stuff/compose.yaml`

```yaml
name: hyaxon-tour-guide-robot

x-tourbot-common: &tourbot-common
  build:
    context: .
    dockerfile: Dockerfile.jazzy
    args:
      TOURBOT_PROXY: ${TOURBOT_PROXY:-http://192.168.100.8:31415}
      TOURBOT_NO_PROXY: ${TOURBOT_NO_PROXY:-localhost,127.0.0.1,::1,192.168.0.0/16,10.0.0.0/8,172.16.0.0/12,xiao-5080,5080-MS-eSport-Z890M}
  image: hyaxon-tour-guide-robot:jazzy
  network_mode: host
  ipc: host
  privileged: false
  gpus: all
  stdin_open: true
  tty: true
  working_dir: /ws
  environment:
    ROS_DOMAIN_ID: ${ROS_DOMAIN_ID:-22}
    RMW_IMPLEMENTATION: ${RMW_IMPLEMENTATION:-rmw_fastrtps_cpp}
    DISPLAY: ${DISPLAY:-:22}
    XAUTHORITY: ${XAUTHORITY:-/home/xiaozy/.Xauthority}
    QT_X11_NO_MITSHM: "1"
    NVIDIA_VISIBLE_DEVICES: all
    NVIDIA_DRIVER_CAPABILITIES: compute,utility,graphics,display
    HTTP_PROXY: ${HTTP_PROXY:-http://192.168.100.8:31415}
    HTTPS_PROXY: ${HTTPS_PROXY:-http://192.168.100.8:31415}
    ALL_PROXY: ${ALL_PROXY:-http://192.168.100.8:31415}
    NO_PROXY: ${NO_PROXY:-localhost,127.0.0.1,::1,192.168.0.0/16,10.0.0.0/8,172.16.0.0/12,xiao-5080,5080-MS-eSport-Z890M}
    http_proxy: ${http_proxy:-http://192.168.100.8:31415}
    https_proxy: ${https_proxy:-http://192.168.100.8:31415}
    all_proxy: ${all_proxy:-http://192.168.100.8:31415}
    no_proxy: ${no_proxy:-localhost,127.0.0.1,::1,192.168.0.0/16,10.0.0.0/8,172.16.0.0/12,xiao-5080,5080-MS-eSport-Z890M}
    PIP_CONFIG_FILE: /etc/pip.conf
    DOCKER_CONFIG: /root/.docker
  volumes:
    - ..:/ws:rw
    - tourbot-build:/ws/build
    - tourbot-install:/ws/install
    - tourbot-log:/ws/log
    - /tmp/.X11-unix:/tmp/.X11-unix:rw
    - /home/xiaozy/.Xauthority:/home/xiaozy/.Xauthority:ro
    - /var/run/docker.sock:/var/run/docker.sock
    - /dev:/dev
  devices:
    - /dev/dri:/dev/dri
  group_add:
    - video
    - render
  security_opt:
    - seccomp=unconfined
  ulimits:
    memlock: -1
    stack: 67108864

services:
  dev:
    <<: *tourbot-common
    command: bash

  build:
    <<: *tourbot-common
    command: bash -lc "rosdep update && rosdep install --from-paths src --ignore-src -r -y && colcon build --symlink-install"

  robot:
    <<: *tourbot-common
    profiles: ["robot"]
    command: bash -lc "source install/setup.bash && ros2 launch tourbot_bringup robot.launch.py"

  mission:
    <<: *tourbot-common
    profiles: ["mission"]
    command: bash -lc "source install/setup.bash && ros2 launch tourbot_bringup mission.launch.py"

  sim:
    <<: *tourbot-common
    profiles: ["sim"]
    command: bash -lc "source install/setup.bash && ros2 launch tourbot_bringup sim.launch.py"

volumes:
  tourbot-build:
  tourbot-install:
  tourbot-log:
```

关键决策：

- `docker_stuff/compose.yaml` 的 `build.context` 是 `.`，用于只把容器构建文件作为 Docker build context；源码挂载使用 `..:/ws`，确保容器内 `/ws` 是工程根目录。
- 代理 build args 和运行时环境变量都提供默认值，正常情况下无需额外导出环境变量。
- `/var/run/docker.sock` 只用于容器内 Docker CLI 复用宿主 Docker daemon；镜像内安装 `docker.io` 是为了提供 `docker` 客户端，不在容器内启动 Docker daemon。这不是 Docker-in-Docker，安全边界等同于授予容器宿主 Docker 控制权，只应在开发容器中使用。
- `network_mode: host`：ROS 2 DDS、真实机器人发现、Nav2/RViz 通信更直接。
- `ipc: host`：降低图像、Gazebo、RViz 共享内存问题。
- `gpus: all`：使用 Compose 原生 GPU 声明，不再写旧式 `runtime: nvidia`。
- `/dev:/dev`：真实 TurtleBot4、相机、串口、LiDAR 调试更方便；若只做仿真，可改为按需挂载 `/dev/video*`、`/dev/ttyUSB*`、`/dev/dri`。
- `privileged: false`：默认不使用特权容器。只有遇到硬件设备权限问题且无法通过 `devices/group_add/udev` 解决时，再临时切换。

---

## 8. 首次构建与编译

进入远端工程：

```bash
ssh xiao-5080
cd /home/xiaozy/4sim/gh-ref/tour-guide-robot/Hyaxon-tour-guide-robot
```

容器相关文件位于 `docker_stuff/`，从工程根目录执行 Compose 时统一加 `-f docker_stuff/compose.yaml`。如果切到 `docker_stuff/` 目录，也可以省略 `-f`。

可选：先验证代理出口。

```bash
curl -I -x http://192.168.100.8:31415 https://github.com
```

创建文件后，构建镜像：

```bash
docker compose -f docker_stuff/compose.yaml build dev
```

安装依赖并编译工作空间：

```bash
docker compose -f docker_stuff/compose.yaml run --rm build
```

如果 rosdep 因某个包无法解析失败，先进入 dev 容器定位：

```bash
docker compose -f docker_stuff/compose.yaml run --rm dev
rosdep check --from-paths src --ignore-src
```

常见处理原则：

- 当前仓库已包含 `apriltag`、`apriltag_msgs`、`apriltag_ros` 源码，rosdep 对这些包应通过 `--ignore-src` 忽略。
- TurtleBot4/Gazebo 包应优先通过 apt 安装到镜像，不建议复制宿主机 `/opt/ros`。
- Python 包优先写入 package.xml 或 Dockerfile，不建议在容器里手工 `pip install` 后不记录。

---

## 9. 日常开发命令

进入开发容器：

```bash
docker compose -f docker_stuff/compose.yaml run --rm dev
```

容器内手动构建：

```bash
colcon build --symlink-install
source install/setup.bash
```

验证 ROS 包可见：

```bash
ros2 pkg list | grep -E 'tourbot|apriltag'
ros2 launch tourbot_bringup robot.launch.py --show-args
ros2 launch tourbot_bringup mission.launch.py --show-args
```

验证 GPU：

```bash
nvidia-smi
```

验证 X11 GUI：

```bash
xeyes
rviz2
```

如果在 VNC 桌面里运行，建议先设置：

```bash
export DISPLAY=:22
```

---

## 10. 启动流程

### 10.1 真实机器人/真实 ROS 网络

终端 1：启动 VNC 并进入桌面。

```bash
~/scripts/start-turbovnc-vnc22.sh
```

终端 2：构建。

```bash
cd /home/xiaozy/4sim/gh-ref/tour-guide-robot/Hyaxon-tour-guide-robot
docker compose -f docker_stuff/compose.yaml run --rm build
```

终端 3：启动导航。

```bash
docker compose -f docker_stuff/compose.yaml --profile robot up robot
```

终端 4：确认 Nav2/RViz 正常后启动 mission。

```bash
docker compose -f docker_stuff/compose.yaml --profile mission up mission
```

停止：

```bash
docker compose -f docker_stuff/compose.yaml --profile robot --profile mission down
```

### 10.2 仿真

```bash
cd /home/xiaozy/4sim/gh-ref/tour-guide-robot/Hyaxon-tour-guide-robot
docker compose -f docker_stuff/compose.yaml run --rm build
docker compose -f docker_stuff/compose.yaml --profile sim up sim
```

若 Gazebo/RViz 黑屏或卡顿：

```bash
nvidia-smi
```

若空闲显存不足，先停止其它 GPU 任务；当前主机已观察到 Python 进程占用约 9.2GB，不建议与 Gazebo 仿真并行。

---

## 11. VirtualGL 与 GUI 策略

默认建议：容器 GUI 直接接入 TurboVNC 的 Xvnc `:22`。

```bash
DISPLAY=:22 docker compose -f docker_stuff/compose.yaml run --rm dev rviz2
```

优点：

- 不依赖物理 Xorg `:0` 的 xhost 权限。
- 与 `docss/102-xiaozy-turbovnc-bp.md` 的 xiaozy 桌面一致。
- 对 RViz2 足够稳定。

当需要物理 GPU OpenGL 渲染时，可在容器命令前使用 VirtualGL，但这要求宿主机 `:0` 对 xiaozy 或容器用户授权：

```bash
DISPLAY=:22 docker compose -f docker_stuff/compose.yaml run --rm dev bash
vglrun -d :0 rviz2
```

如果报 `Could not open display :0`，按 `docss/102-xiaozy-turbovnc-bp.md` 第 5 节处理 `xhost` 授权。最可靠方式是由能访问物理 `:0` 的用户执行：

```bash
DISPLAY=:0 xhost +si:localuser:xiaozy
```

注意：容器内如果以 root 运行，可能还需要授权 root：

```bash
DISPLAY=:0 xhost +si:localuser:root
```

安全建议：不要使用 `xhost +` 全局放开访问。

---

## 12. ROS 2 网络建议

Compose 中默认：

```yaml
ROS_DOMAIN_ID: ${ROS_DOMAIN_ID:-22}
RMW_IMPLEMENTATION: ${RMW_IMPLEMENTATION:-rmw_fastrtps_cpp}
```

建议：

- 如果局域网已有其它 ROS 2 系统，先确认 domain，避免串话。
- xiaozy 的 VNC display 是 `:22`，`ROS_DOMAIN_ID=22` 只是便于记忆，不是技术绑定。
- 若 TurtleBot4 已使用固定 domain，应以机器人实际配置为准，例如：

```bash
ROS_DOMAIN_ID=0 docker compose -f docker_stuff/compose.yaml --profile robot up robot
```

检查发现：

```bash
ros2 topic list
ros2 node list
ros2 doctor --report
```

---

## 13. 硬件设备挂载策略

当前 compose 使用：

```yaml
volumes:
  - /dev:/dev
devices:
  - /dev/dri:/dev/dri
```

这是开发期方便方案。进入稳定运行后，建议收敛为最小设备集：

| 设备 | 可能路径 | 用途 |
|---|---|---|
| GPU render | `/dev/dri` | RViz/Gazebo/OpenGL |
| Camera | `/dev/video*`、OAK-D/DepthAI USB 设备 | AprilTag 图像输入 |
| LiDAR | `/dev/ttyUSB*` 或网络端口 | RPLIDAR/底盘传感 |
| TurtleBot4 网络 | host network | ROS 2 DDS/机器人通信 |

收敛示例：

```yaml
devices:
  - /dev/dri:/dev/dri
  - /dev/video0:/dev/video0
  - /dev/ttyUSB0:/dev/ttyUSB0
```

如果设备权限不足，优先方案是把 xiaozy 加入正确宿主组并重新登录；不要直接把 `privileged: true` 当作长期方案。

---

## 14. 验收清单

| # | 命令 | 通过标准 |
|---|---|---|
| 1 | `docker compose -f docker_stuff/compose.yaml config` | YAML 无错误 |
| 2 | `docker compose -f docker_stuff/compose.yaml build dev` | 镜像构建成功 |
| 3 | `docker compose -f docker_stuff/compose.yaml run --rm dev nvidia-smi` | 显示 RTX 5080 |
| 4 | `DISPLAY=:22 docker compose -f docker_stuff/compose.yaml run --rm dev xeyes` | VNC 桌面出现窗口 |
| 5 | `docker compose -f docker_stuff/compose.yaml run --rm build` | `colcon build` 成功 |
| 6 | `docker compose -f docker_stuff/compose.yaml run --rm dev ros2 pkg list | grep tourbot` | 能看到工程包 |
| 7 | `docker compose -f docker_stuff/compose.yaml run --rm dev ros2 launch tourbot_bringup robot.launch.py --show-args` | launch 文件解析成功 |
| 8 | `docker compose -f docker_stuff/compose.yaml --profile sim up sim` | Gazebo/RViz 能启动，或在当前项目限制内给出明确缺失 |
| 9 | `docker compose -f docker_stuff/compose.yaml --profile robot up robot` | Nav2/RViz 启动，无 ROS 包缺失 |
| 10 | `docker compose -f docker_stuff/compose.yaml --profile mission up mission` | 行为 server 和 mission node 启动 |

---

## 15. 故障排查

### 15.1 `could not select device driver "" with capabilities: [[gpu]]`

说明 Docker 没正确识别 NVIDIA runtime。当前主机检查已显示 `nvidia` runtime 存在；如果后续失效，检查：

```bash
docker info | grep -i runtime
nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

`xiaozy` 不在 sudo 组时，需要管理员执行后两条。

### 15.2 RViz/Gazebo 无法打开窗口

检查 VNC：

```bash
pgrep -af 'Xvnc.*:22'
ls -l /tmp/.X11-unix/X22
```

检查容器环境：

```bash
docker compose -f docker_stuff/compose.yaml run --rm dev bash -lc 'echo $DISPLAY; ls -l /tmp/.X11-unix; xeyes'
```

如果 `Xauthority` 失败，可临时在 VNC 终端中执行：

```bash
xhost +si:localuser:root
```

长期方案是让容器以宿主 UID 运行，而不是扩大 xhost 权限。可在 compose 中增加：

```yaml
user: "1005:1005"
```

但要同步处理 `/ws/build`、`/ws/install` volume 权限。

### 15.3 `colcon build` 找不到 TurtleBot4 包

先确认 apt 包名：

```bash
docker compose -f docker_stuff/compose.yaml run --rm dev bash -lc 'apt-cache search ros-jazzy-turtlebot4 | sort'
```

根据实际包名调整 Dockerfile。不要把宿主机 `/opt/ros/jazzy` bind mount 到容器覆盖镜像内 ROS 安装。

### 15.4 ROS 2 看不到机器人话题

使用 host network 后，一般不是 Docker NAT 问题。重点查：

```bash
echo $ROS_DOMAIN_ID
ros2 daemon stop
ros2 daemon start
ros2 topic list
```

确认 TurtleBot4、容器和其它 ROS 2 节点使用相同 `ROS_DOMAIN_ID` 和兼容 RMW。

### 15.5 容器内 apt/pip/git/GitHub 未走代理

进入容器检查：

```bash
docker compose -f docker_stuff/compose.yaml run --rm dev bash
env | grep -i proxy
cat /etc/apt/apt.conf.d/99proxy
cat /etc/pip.conf
git config --system --get http.proxy
git config --system --get https.proxy
cat /root/.docker/config.json
```

快速验证：

```bash
apt-get update
pip config list
git ls-remote https://github.com/ros2/ros2.git HEAD
```

如果 `git` 或 `pip` 仍不走代理，优先检查是否被命令行参数、用户级配置或 `NO_PROXY` 覆盖。

### 15.6 GPU 显存不足

检查：

```bash
nvidia-smi
```

当前主机已出现 Python 进程占用约 9.2GB 的情况。Gazebo/RViz 运行前建议释放显存，否则会表现为 GUI 卡顿、Gazebo 崩溃或 CUDA/OpenGL 初始化失败。

---

## 16. 推荐执行顺序

1. 在 `xiao-5080` 工程根目录新增 `docker_stuff/.dockerignore`、`docker_stuff/ros_entrypoint.sh`、`docker_stuff/Dockerfile.jazzy`、`docker_stuff/compose.yaml`。
2. 执行 `docker compose -f docker_stuff/compose.yaml config`，先验证 Compose 文件语法。
3. 执行 `docker compose -f docker_stuff/compose.yaml build dev`，固定基础依赖。
4. 执行 `docker compose -f docker_stuff/compose.yaml run --rm dev nvidia-smi`，验证 GPU 注入。
5. 在 VNC 桌面中执行 `DISPLAY=:22 docker compose -f docker_stuff/compose.yaml run --rm dev xeyes`，验证 GUI。
6. 执行 `docker compose -f docker_stuff/compose.yaml run --rm build`，验证 rosdep 和 `colcon build`。
7. 执行 `docker compose -f docker_stuff/compose.yaml run --rm dev ros2 launch tourbot_bringup robot.launch.py --show-args`，验证 launch 解析。
8. 仿真优先执行 `docker compose -f docker_stuff/compose.yaml --profile sim up sim`；真实机器人优先执行 `docker compose -f docker_stuff/compose.yaml --profile robot up robot`。
9. Nav2/话题稳定后，再执行 `docker compose -f docker_stuff/compose.yaml --profile mission up mission`。
10. 将实际通过的命令和任何包名修正回写到 README 或后续 `docss/007-*` 验收文档。

---

## 17. 当前建议结论

在 `xiao-5080` 上运行当前工程，推荐使用 Docker Compose 单镜像多服务方案：

- `dev` 用于日常调试。
- `build` 用于可重复编译。
- `robot` 用于真实 TurtleBot4/Nav2/RViz。
- `mission` 用于 AprilTag 感知、行为 server 和任务控制。
- `sim` 用于 Gazebo 仿真验证。

该方案与当前 RTX 5080、Docker NVIDIA runtime、TurboVNC `:22` 的实际状态匹配。落地时优先保证构建、GPU、GUI 三项验收通过，再处理真实机器人设备权限和 ROS 2 domain 配置。

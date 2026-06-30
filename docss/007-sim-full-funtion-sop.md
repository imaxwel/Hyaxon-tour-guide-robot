# Tour Guide Robot 完整仿真功能复现 SOP

> 编写日期：2026-06-30  
> 目标主机：`xiao-5080` / `5080-MS-eSport-Z890M` / Ubuntu 24.04  
> 目标仓库：`/home/xiaozy/4sim/gh-ref/tour-guide-robot/Hyaxon-tour-guide-robot`  
> 操作原则：所有命令都在 `xiao-5080` 上执行，不在 Dell notebook 本机执行。  
> 目标：用当前仓库现有代码复现 TurtleBot4 tour guide robot 的仿真、导航、AprilTag 感知、landmark tour、tag 对齐、门等待、门穿越等已有功能。

---

## 0. 当前远端状态核对

在 Dell notebook 只做 SSH 入口：

```bash
ssh xiao-5080
cd /home/xiaozy/4sim/gh-ref/tour-guide-robot/Hyaxon-tour-guide-robot
```

确认确实在远端主机：

```bash
hostname
pwd
git branch --show-current
```

期望：

```text
5080-MS-eSport-Z890M
/home/xiaozy/4sim/gh-ref/tour-guide-robot/Hyaxon-tour-guide-robot
x5080
```

本 SOP 依据 2026-06-30 在远端实际检查结果整理：

- Docker 镜像已存在：`hyaxon-tour-guide-robot:jazzy`。
- Compose 文件：`docker_stuff/compose.yaml`。
- ROS 2 发行版：Jazzy。
- 仓库内可构建包共 9 个：`apriltag`、`apriltag_msgs`、`apriltag_ros`、`tourbot_interfaces`、`tourbot_bringup`、`tourbot_landmarks`、`tourbot_mission`、`tourbot_behaviors`、`tourbot_perception`。
- 图形桌面：TurboVNC `DISPLAY=:22`，RFB `127.0.0.1:5922`。
- Compose 将 `/ws/build`、`/ws/install`、`/ws/log` 挂载到 Docker 命名卷，宿主仓库下 root-owned 的 `build/install/log` 不是容器运行时真正使用的构建空间。

资源检查：

```bash
nvidia-smi --query-gpu=name,memory.used,memory.free,utilization.gpu --format=csv,noheader
pgrep -af 'Xvnc.*:22'
ss -tlnp 'sport = :5922'
```

建议在启动 Gazebo + RViz 前至少保留 5-6GB 空闲显存。若 GPU 被其它 Python 进程占用较多，先协调释放资源。

---

## 1. 功能覆盖范围

当前仓库已有功能按 ROS 包划分如下：

| 功能 | 包/入口 | 复现方式 |
|---|---|---|
| TurtleBot4 Gazebo 仿真 | `tourbot_bringup/launch/sim.launch.py` | 启动 Gazebo Harmonic、TurtleBot4、bridge、可选 Nav2/RViz |
| 地图定位和 Nav2 | `tourbot_bringup/launch/robot.launch.py` 或 sim 内 nav2/localization | 加载 `cardboard_city/map_area.yaml` 或官方 warehouse map |
| AprilTag 检测 | `tourbot_perception/launch/apriltag_pipeline.launch.py` | `apriltag_ros` 订阅 `/oakd/rgb/preview/image_raw` 和 `/oakd/rgb/preview/camera_info`，发布 `/detections` |
| Landmark 数据 | `tourbot_landmarks/config/cardboard_city/landmarks.yaml` | `tour_deliberation_node` 固定加载 `cardboard_city` |
| Tour mission | `tourbot_mission/tour_deliberation_node.py` | 最近邻顺序访问 landmarks，调用 Nav2 和行为 action |
| AprilTag 对齐 | `align_to_apriltag_server` | action `/align_to_apriltag`，发布 `/cmd_vel` |
| 等待门 tag 消失 | `wait_for_tag_removed_server` | action `/wait_for_tag_removed`，订阅 `/detections` |
| 门穿越 | `door_behavior_server` | action `/door_traverse`，订阅 `/odom`，发布 `/cmd_vel` |

当前 landmarks：

```text
home: tag_id=0, (0, 0), NORTH
door_outward: tag_id=1, (3.14, 0), SOUTH
door_inward: tag_id=2, (1.71, 0), NORTH
goal_3: tag_id=3, (0.942, 0.495), WEST
goal_4: tag_id=4, (1.33, -0.2), EAST
goal_5: tag_id=5, (3.36, -0.2), EAST
goal_6: tag_id=6, (2.34, -0.647), WEST
goal_7: tag_id=7, (2.35, 0.673), EAST
```

门规则由代码固定：

- `tag_id=1`：outward door，等待 tag 消失后直接向前穿越。
- `tag_id=2`：inward door，先转身/后退/转回，再向前穿越。
- 其它 tag：对齐后旋转 180 度离开 landmark。

---

## 2. 图形桌面接入

如果 VNC 已启动，Dell notebook 上建立 tunnel：

```bash
ssh -N -L 5922:127.0.0.1:5922 xiao-5080
```

本机打开 TurboVNC Viewer：

```bash
/opt/TurboVNC/bin/vncviewer localhost::5922
```

如果远端 VNC 未启动，在 `xiao-5080` 上执行：

```bash
~/scripts/start-turbovnc-vnc22.sh
```

容器默认使用：

```text
DISPLAY=:22
XAUTHORITY=/home/xiaozy/.Xauthority
```

RViz2 和 Gazebo GUI 应在 VNC 桌面中可见。

---

## 3. 容器和工作空间构建

所有 Compose 命令都从仓库根目录执行：

```bash
cd /home/xiaozy/4sim/gh-ref/tour-guide-robot/Hyaxon-tour-guide-robot
```

检查 Compose 和 GPU：

```bash
docker --version
docker compose version
docker info --format '{{json .Runtimes}}' | grep -o nvidia
nvidia-smi
```

构建镜像：

```bash
docker compose -f docker_stuff/compose.yaml build dev
```

构建 ROS 工作空间：

```bash
docker compose -f docker_stuff/compose.yaml run --rm build
```

快速验证工作空间可从干净路径重新构建，不影响当前命名卷里的 `/ws/install`：

```bash
docker compose -f docker_stuff/compose.yaml run --rm --no-deps dev bash -lc \
  'source /opt/ros/jazzy/setup.bash && \
   colcon --log-base /tmp/tourbot-log build \
     --symlink-install \
     --build-base /tmp/tourbot-build \
     --install-base /tmp/tourbot-install'
```

2026-06-30 远端已验证该命令成功：

```text
Summary: 9 packages finished [17.3s]
```

进入开发容器：

```bash
docker compose -f docker_stuff/compose.yaml run --rm --no-deps dev
```

容器内检查包：

```bash
source install/setup.bash
ros2 pkg list | grep -E 'tourbot|apriltag|turtlebot4'
```

应至少看到：

```text
apriltag_msgs
apriltag_ros
tourbot_behaviors
tourbot_bringup
tourbot_interfaces
tourbot_landmarks
tourbot_mission
tourbot_perception
turtlebot4_gz_bringup
turtlebot4_navigation
turtlebot4_viz
```

---

## 4. 推荐仿真模式

### 4.1 纯仿真隔离建议

Compose 使用 `network_mode: host`，ROS 2 DDS 会在局域网广播。若局域网中有真实 TurtleBot4 或其它同域 ROS 节点，为避免误控真实机器人，纯仿真建议用临时 domain：

```bash
export ROS_DOMAIN_ID=142
```

如果需要接入当前已运行的真实/仿真 graph，则使用 Compose 默认值：

```bash
export ROS_DOMAIN_ID=42
```

### 4.2 官方 warehouse 仿真，最稳启动路径

该路径复现 TurtleBot4 Gazebo、bridge、Nav2、RViz 基础能力，适合作为第一层 smoke test：

```bash
docker compose -f docker_stuff/compose.yaml --profile sim up sim
```

该服务实际执行：

```bash
source install/setup.bash
ros2 launch tourbot_bringup sim.launch.py
```

`use_custom_sim` 默认是 `false`，会走 TurtleBot4 官方 warehouse world，同时开启：

- Gazebo Harmonic
- TurtleBot4 spawn
- ROS-Gazebo bridge
- localization
- Nav2
- RViz

另开一个远端终端查看 ROS graph：

```bash
docker compose -f docker_stuff/compose.yaml run --rm --no-deps dev bash -lc \
  'source install/setup.bash && ros2 node list && ros2 action list -t && ros2 topic list -t'
```

#### 4.2 FAQ: Gazebo 启动一会儿后退出

2026-06-30 在 `xiao-5080` 上复现过该问题。表面现象是 `docker compose -f docker_stuff/compose.yaml --profile sim up sim` 运行一会儿后 Gazebo 退出，随后 controller spawner 报超时。

先抓关键日志：

```bash
docker compose -f docker_stuff/compose.yaml logs sim 2>&1 | \
  grep -nE 'symbol lookup error|diagnostic_updater|controller_manager|spawner|Downloading model|SIGKILL|failed to create dri2'
```

如果看到类似下面的日志，根因是镜像里的 ROS apt 包 ABI 混用，不是 Gazebo GUI 本身崩溃：

```text
libnav2_lifecycle_manager_core.so: undefined symbol: ... diagnostic_updater::Updater...
gz sim server: symbol lookup error: /opt/ros/jazzy/lib/libcontroller_manager.so: undefined symbol: ... diagnostic_updater::Updater...
spawner_joint_state_broadcaster: Could not contact service /controller_manager/list_controllers
spawner_diffdrive_controller: Could not contact service /controller_manager/list_controllers
```

实测原因：当前旧镜像里 `controller_manager`、`gz_ros2_control`、Nav2 是 2026-06-15 一批新包，但 `ros-jazzy-rclcpp` 和 `ros-jazzy-diagnostic-updater` 仍停在 2026-04-12。`controller_manager` 需要新版 `diagnostic_updater::Updater(..., double, bool)` 符号，旧库没有这个符号，所以 Gazebo server 在加载 ros2_control 插件时退出。

确认命令：

```bash
docker compose -f docker_stuff/compose.yaml run --rm --no-deps dev bash -lc '
  apt-get update >/dev/null
  apt-cache policy ros-jazzy-rclcpp ros-jazzy-diagnostic-updater ros-jazzy-controller-manager
  nm -D /opt/ros/jazzy/lib/libdiagnostic_updater.so | c++filt | grep "diagnostic_updater::Updater::Updater" || true
'
```

临时修复当前已创建的 `sim` 容器：

```bash
docker compose -f docker_stuff/compose.yaml exec -T sim bash -lc '
  apt-get update &&
  apt-get install --only-upgrade -y \
    ros-jazzy-rclcpp \
    ros-jazzy-rclcpp-action \
    ros-jazzy-rclcpp-components \
    ros-jazzy-rclcpp-lifecycle \
    ros-jazzy-diagnostic-updater
'

docker compose -f docker_stuff/compose.yaml restart sim
```

如果 `sim` 容器已经退出，直接走永久修复路径。

永久修复路径：本仓库 `docker_stuff/Dockerfile.jazzy` 已显式安装/升级以下包，重建镜像即可让新容器不再复现该 ABI 问题：

```text
ros-${ROS_DISTRO}-rclcpp
ros-${ROS_DISTRO}-rclcpp-action
ros-${ROS_DISTRO}-rclcpp-components
ros-${ROS_DISTRO}-rclcpp-lifecycle
ros-${ROS_DISTRO}-diagnostic-updater
```

重建和启动：

```bash
docker compose -f docker_stuff/compose.yaml down
docker compose -f docker_stuff/compose.yaml build --no-cache dev
docker compose -f docker_stuff/compose.yaml run --rm build
ROS_DOMAIN_ID=142 docker compose -f docker_stuff/compose.yaml --profile sim up --force-recreate sim
```

验证修复：

```bash
docker compose -f docker_stuff/compose.yaml exec -T sim bash -lc '
  source /opt/ros/jazzy/setup.bash
  nm -D /opt/ros/jazzy/lib/libdiagnostic_updater.so | c++filt | grep "double, unsigned char"
  ldd -r /opt/ros/jazzy/lib/libcontroller_manager.so 2>&1 | grep "undefined symbol" || true
  ros2 service list | grep /controller_manager/list_controllers
'
```

`ldd -r` 没有 `undefined symbol`，且 `/controller_manager/list_controllers` 出现，说明 ros2_control 已加载。

另一个容易误判的问题是首次运行官方 warehouse world 会从 Gazebo Fuel 下载大量模型。日志里会持续出现 `Downloading model [fuel.gazebosim.org/...]`。如果只有下载和 spawner timeout，没有 `symbol lookup error`，通常是首次下载太慢导致 spawner 30 秒超时；等模型缓存完成后重启一次即可：

```bash
docker compose -f docker_stuff/compose.yaml restart sim
```

如果同时开着 `robot`、`mission` 和 `sim`，ROS graph 会出现重复节点名，排查 smoke test 时优先停止其它服务或使用独立 `ROS_DOMAIN_ID`。最干净路径是：

```bash
docker compose -f docker_stuff/compose.yaml down
ROS_DOMAIN_ID=142 docker compose -f docker_stuff/compose.yaml --profile sim up --force-recreate sim
```

### 4.3 当前仓库 cardboard_city world/map 仿真

当前仓库实际 world 文件是：

```text
src/tourbot_bringup/worlds/cardboard_city/world.sdf
```

已安装到容器：

```text
/ws/install/tourbot_bringup/share/tourbot_bringup/worlds/cardboard_city/world.sdf
```

注意：`sim.launch.py` 的默认 `custom_world` 写成了 `cardboard_city.sdf`，但仓库没有这个文件。并且 TurtleBot4 下游 launch 会自动追加 `.sdf`，因此传绝对路径时不要带 `.sdf` 后缀。

正确命令：

```bash
docker compose -f docker_stuff/compose.yaml run --rm --no-deps dev bash -lc '
  source install/setup.bash
  ros2 launch tourbot_bringup sim.launch.py \
    use_custom_sim:=true \
    custom_world:=/ws/install/tourbot_bringup/share/tourbot_bringup/worlds/cardboard_city/world \
    custom_map:=/ws/install/tourbot_bringup/share/tourbot_bringup/maps/cardboard_city/map_area.yaml \
    rviz:=true
'
```

当前 `world.sdf` 只包含地面、光照、Gazebo GUI 和基础系统插件，尚未包含 cardboard city 墙体、障碍物、门或 AprilTag 模型。因此它能复现 Gazebo/TurtleBot4/Nav2 框架，但不能单靠视觉自动产生所有 landmark tag。完整 tour 行为需要：

- 在 Gazebo world 中补放 AprilTag 可见模型，或
- 使用第 7 节的 topic/action 方式对各行为做功能级仿真验证。

---

## 5. 启动当前仓库完整 robot + mission graph

如果不使用 `sim` 服务，而是按仓库 README 的两段式启动：

终端 A，启动 robot/Nav2/RViz：

```bash
docker compose -f docker_stuff/compose.yaml --profile robot up robot
```

终端 B，启动 perception/behavior/mission：

```bash
docker compose -f docker_stuff/compose.yaml --profile mission up mission
```

等价裸命令：

```bash
source install/setup.bash
ros2 launch tourbot_bringup robot.launch.py
```

```bash
source install/setup.bash
ros2 launch tourbot_bringup mission.launch.py
```

`mission.launch.py` 启动顺序：

1. `apriltag_pipeline.launch.py`
2. 2.0s 后 `align_to_apriltag_server`
3. 2.5s 后 `wait_for_tag_removed_server`
4. 3.0s 后 `door_behavior_server`
5. 10.0s 后 `tour_deliberation_node`

当前远端已观测到 `robot` 和 `mission` 两个服务可启动，ROS graph 中出现：

```text
/align_to_apriltag_server
/apriltag
/door_behavior_server
/tour_deliberation_node
/wait_for_tag_removed_server
```

关键 action：

```text
/align_to_apriltag [tourbot_interfaces/action/AlignToAprilTag]
/door_traverse [tourbot_interfaces/action/DoorTraverse]
/navigate_to_pose [nav2_msgs/action/NavigateToPose]
/wait_for_tag_removed [tourbot_interfaces/action/WaitForTagRemoved]
```

关键 topic：

```text
/cmd_vel [geometry_msgs/msg/TwistStamped]
/detections [apriltag_msgs/msg/AprilTagDetectionArray]
/map [nav_msgs/msg/OccupancyGrid]
/oakd/rgb/preview/camera_info [sensor_msgs/msg/CameraInfo]
/oakd/rgb/preview/image_raw [sensor_msgs/msg/Image]
/odom [nav_msgs/msg/Odometry]
/scan [sensor_msgs/msg/LaserScan]
/tf [tf2_msgs/msg/TFMessage]
```

日志查看：

```bash
docker compose -f docker_stuff/compose.yaml logs --tail=120 robot
docker compose -f docker_stuff/compose.yaml logs --tail=160 mission
```

停止当前 stack：

```bash
docker compose -f docker_stuff/compose.yaml down
```

---

## 6. Mission 自动流程复现

`tour_deliberation_node` 固定加载：

```text
tourbot_landmarks/config/cardboard_city/landmarks.yaml
```

流程：

1. 设置 `home` 为初始位姿，连续发布 10 次 initial pose。
2. 等待 Nav2 active。
3. 从 home 开始，对 landmarks 做最近邻贪心排序。
4. 对每个 landmark 调用 Nav2 `startToPose()`。
5. 到点后调用 `/align_to_apriltag`：`timeout_sec=30.0`，`x_tolerance_px=7.0`。
6. 若 tag 是 1 或 2，执行门流程：`/wait_for_tag_removed` 后调用 `/door_traverse`。
7. 非门 landmark：对当前 landmark pose 旋转 180 度。
8. 所有 landmarks 访问完成后返回 home。

完整 mission 能自动跑通的前提：

- Nav2 有可用 `/map`、`/scan`、`/odom`、`/tf`。
- `/oakd/rgb/preview/image_raw` 和 `/oakd/rgb/preview/camera_info` 可用。
- AprilTag pipeline 能在对应 landmark 附近发布目标 tag 到 `/detections`。
- 门 tag 1/2 能先可见，再在人工开门或仿真控制后从 `/detections` 消失至少 3 秒。
- `/cmd_vel` 控制的是仿真机器人或安全隔离机器人。

如果当前 cardboard_city world 没有真实 tag 模型，mission 会在对齐阶段搜索或超时。这不是 action server 构建失败，而是仿真场景资产缺失。

---

## 7. 功能级仿真验证

本节用于在没有完整 AprilTag 场景资产时，仍然复现仓库已有行为逻辑。建议先只启动 Gazebo/Nav2 或确保 `/cmd_vel` 指向仿真机器人，再启动单个行为 server 做验证。

进入一个同 ROS domain 的 dev 容器：

```bash
docker compose -f docker_stuff/compose.yaml run --rm --no-deps dev bash
source install/setup.bash
```

### 7.1 AprilTag perception pipeline

启动：

```bash
ros2 launch tourbot_perception apriltag_pipeline.launch.py
```

输入：

```text
/oakd/rgb/preview/image_raw [sensor_msgs/msg/Image]
/oakd/rgb/preview/camera_info [sensor_msgs/msg/CameraInfo]
```

输出：

```text
/detections [apriltag_msgs/msg/AprilTagDetectionArray]
```

检查：

```bash
ros2 topic hz /oakd/rgb/preview/image_raw
ros2 topic hz /oakd/rgb/preview/camera_info
ros2 topic echo /detections --once
```

AprilTag 参数：

```text
family: 36h11
size: 0.162
max_hamming: 0
z_up: true
```

### 7.2 `/align_to_apriltag` 对齐行为

启动 server：

```bash
ros2 run tourbot_behaviors align_to_apriltag_server
```

接口：

```text
action: /align_to_apriltag [tourbot_interfaces/action/AlignToAprilTag]
sub: /detections [apriltag_msgs/msg/AprilTagDetectionArray]
sub: /oakd/rgb/preview/camera_info [sensor_msgs/msg/CameraInfo]
pub: /cmd_vel [geometry_msgs/msg/TwistStamped]
```

在另一个终端持续发布相机信息：

```bash
ros2 topic pub -r 10 /oakd/rgb/preview/camera_info sensor_msgs/msg/CameraInfo \
  '{width: 640, height: 480}'
```

发布一个已居中的 tag 3：

```bash
ros2 topic pub -r 10 /detections apriltag_msgs/msg/AprilTagDetectionArray \
  "{detections: [{family: '36h11', id: 3, hamming: 0, goodness: 1.0, decision_margin: 100.0, centre: {x: 320.0, y: 240.0}, corners: [{x: 300.0, y: 220.0}, {x: 340.0, y: 220.0}, {x: 340.0, y: 260.0}, {x: 300.0, y: 260.0}], homography: [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0], header: {frame_id: 'oakd_rgb_camera_optical_frame'}}]}"
```

发送 action：

```bash
ros2 action send_goal /align_to_apriltag \
  tourbot_interfaces/action/AlignToAprilTag \
  '{tag_id: 3, timeout_sec: 5.0, x_tolerance_px: 7.0}' \
  --feedback
```

期望：

- tag 居中时 result `success: true`，message 类似 `Aligned to tag 3.`。
- tag 不存在时 server 以 `SEARCH_ANGULAR_SPEED=0.20` 发布旋转 `/cmd_vel`，直到超时。
- tag 偏左/偏右时按 `ALIGN_KP=0.003` 计算角速度，限幅 `MAX_ANGULAR_SPEED=0.30`。

### 7.3 `/wait_for_tag_removed` 门等待行为

启动 server：

```bash
ros2 run tourbot_behaviors wait_for_tag_removed_server
```

直接验证“tag 缺失后成功”：

```bash
ros2 topic pub -r 10 /detections apriltag_msgs/msg/AprilTagDetectionArray '{detections: []}'
```

```bash
ros2 action send_goal /wait_for_tag_removed \
  tourbot_interfaces/action/WaitForTagRemoved \
  '{tag_id: 1, timeout_sec: 10.0, missing_duration_sec: 2.0}' \
  --feedback
```

期望：2 秒后 result `success: true`。

验证“先可见，再消失”：

1. 持续发布 tag 1 detection。
2. 发送 `/wait_for_tag_removed` goal。
3. 停止 tag 1 publisher，改发 `{detections: []}`。
4. 等待 `missing_duration_sec` 后 action 成功。

### 7.4 `/door_traverse` 门穿越行为

只在 Gazebo 仿真或安全隔离机器人上执行，因为该 action 会发布 `/cmd_vel`。

启动 server：

```bash
ros2 run tourbot_behaviors door_behavior_server
```

接口：

```text
action: /door_traverse [tourbot_interfaces/action/DoorTraverse]
sub: /odom [nav_msgs/msg/Odometry]
pub: /cmd_vel [geometry_msgs/msg/TwistStamped]
```

检查 odom：

```bash
ros2 topic echo /odom --once
```

outward door 小距离测试：

```bash
ros2 action send_goal /door_traverse \
  tourbot_interfaces/action/DoorTraverse \
  '{tag_id: 1, backup_distance: 0.0, backup_speed: 0.0, wait_seconds: 1.0, forward_distance: 0.2, forward_speed: 0.05}' \
  --feedback
```

inward door 小距离测试：

```bash
ros2 action send_goal /door_traverse \
  tourbot_interfaces/action/DoorTraverse \
  '{tag_id: 2, backup_distance: 0.2, backup_speed: 0.05, wait_seconds: 1.0, forward_distance: 0.2, forward_speed: 0.05}' \
  --feedback
```

默认参数来自 `door_behavior_server`：

```text
backup_distance_default: 0.9
backup_speed_default: 0.15
wait_seconds_default: 3.0
forward_distance_default: 1.5
forward_speed_default: 0.18
control_rate_hz: 20.0 in code, 10.0 if using config/door_behavior.yaml
```

注意：`mission.launch.py` 直接启动 `door_behavior_server`，没有加载 `config/door_behavior.yaml`，所以按代码默认 `control_rate_hz=20.0`。单独使用 `door_behavior.launch.py` 才会加载 YAML，但该 launch 另有已知问题，见第 9 节。

### 7.5 Nav2 单点导航

确保 `/map`、`/tf`、`/odom`、`/scan` 正常：

```bash
ros2 topic echo /map --once
ros2 topic echo /odom --once
ros2 topic echo /scan --once
ros2 run tf2_ros tf2_echo map base_link
```

发送一个小范围目标，坐标需落在当前 map 可通行区域内：

```bash
ros2 action send_goal /navigate_to_pose nav2_msgs/action/NavigateToPose \
  "{pose: {header: {frame_id: 'map'}, pose: {position: {x: 0.5, y: 0.0, z: 0.0}, orientation: {w: 1.0}}}}" \
  --feedback
```

如果使用 `cardboard_city` map，优先从 `landmarks.yaml` 中选靠近 home 的点，如 `(0.942, 0.495)`。

---

## 8. 完整 tour 的可复现实验顺序

推荐按以下顺序做验收，任何一步失败都先停在该层排查：

1. 远端环境：VNC、GPU、Docker、Compose 正常。
2. 构建：`colcon build` 9 个包全部成功。
3. 仿真底座：Gazebo 中能看到 TurtleBot4，`/odom`、`/scan`、`/tf` 有数据。
4. Nav2：`/navigate_to_pose` 小目标成功。
5. AprilTag pipeline：相机 topic 有数据，真实或仿真 tag 可产生 `/detections`。
6. 对齐行为：`/align_to_apriltag` 在 tag 居中时成功，tag 偏移时发布角速度。
7. 门等待：`/wait_for_tag_removed` 在 tag 消失指定时间后成功。
8. 门穿越：`/door_traverse` 对 tag 1/2 都能在仿真里完成小距离动作。
9. mission：启动 `mission.launch.py`，确认 `tour_deliberation_node` 能依序调用 Nav2 和三个行为 action。

检查 action 列表：

```bash
ros2 action list -t | grep -E 'align_to_apriltag|wait_for_tag_removed|door_traverse|navigate_to_pose'
```

检查 topic：

```bash
ros2 topic list -t | grep -E 'detections|oakd|odom|scan|cmd_vel|map|tf'
```

检查节点：

```bash
ros2 node list | grep -E 'apriltag|align|wait|door|tour|nav|amcl|controller|planner'
```

---

## 9. 当前代码/场景已知问题和规避

### 9.1 `sim.launch.py` 自定义 world 默认路径不匹配

现象：默认 `custom_world` 指向：

```text
worlds/cardboard_city/cardboard_city.sdf
```

实际文件：

```text
worlds/cardboard_city/world.sdf
```

规避：启动时显式传不带 `.sdf` 的路径：

```bash
custom_world:=/ws/install/tourbot_bringup/share/tourbot_bringup/worlds/cardboard_city/world
```

### 9.2 当前 cardboard_city world 不是完整场景资产

`world.sdf` 当前只有 ground plane、灯光、GUI 和系统插件，没有墙体、门、AprilTag 模型。它能启动 Gazebo 框架，但不能自动完成视觉 tour。完整自动 tour 需要补场景资产，或用第 7 节 topic/action 方法复现行为逻辑。

### 9.3 `door_behavior.launch.py` 引用了缺失节点

`tourbot_behaviors/setup.py` 和 `door_behavior.launch.py` 引用：

```text
manual_door_override_node
```

但当前源码目录没有 `manual_door_override_node.py`。因此不要用 `ros2 launch tourbot_behaviors door_behavior.launch.py` 作为主路径。当前可用路径是：

```bash
ros2 run tourbot_behaviors door_behavior_server
```

或使用：

```bash
ros2 launch tourbot_bringup mission.launch.py
```

### 9.4 `landmark_task_server.py` 未实现

当前文件内容只有 TODO，`DoLandmarkTask.action` 也未接入 mission。SOP 不把它列为可运行功能，只列为接口占位。

### 9.5 `door_detector_node.py` 已标记不再需要

该文件注释说明功能已由 `tourbot_perception` 和 `wait_for_tag_removed_server` 覆盖。当前 mission 不依赖它。

### 9.6 `/cmd_vel` 类型是 `TwistStamped`

Nav2 参数中 `enable_stamped_cmd_vel: true`，行为 server 也发布 `geometry_msgs/msg/TwistStamped`。手动调试不要发 `geometry_msgs/msg/Twist` 到 `/cmd_vel`。

---

## 10. 快速恢复命令

停止 Compose stack：

```bash
docker compose -f docker_stuff/compose.yaml down
```

重建工作空间：

```bash
docker compose -f docker_stuff/compose.yaml run --rm build
```

启动仿真：

```bash
docker compose -f docker_stuff/compose.yaml --profile sim up sim
```

启动 robot + mission：

```bash
docker compose -f docker_stuff/compose.yaml --profile robot up robot
```

```bash
docker compose -f docker_stuff/compose.yaml --profile mission up mission
```

查看状态：

```bash
docker compose -f docker_stuff/compose.yaml ps --all
docker compose -f docker_stuff/compose.yaml logs --tail=120 robot
docker compose -f docker_stuff/compose.yaml logs --tail=160 mission
```

进入同环境调试：

```bash
docker compose -f docker_stuff/compose.yaml run --rm --no-deps dev bash
source install/setup.bash
```

---

## 11. 验收标准

认为“当前仓库已有机器人功能已完整仿真复现”需要满足：

- `colcon build --symlink-install` 成功构建 9 个包。
- Gazebo 或等效仿真环境中 `/odom`、`/scan`、`/tf`、`/cmd_vel`、`/map` 正常。
- Nav2 `/navigate_to_pose` 可完成至少一个小目标。
- AprilTag pipeline 能从相机输入发布 `/detections`，或用 synthetic `/detections` 完成行为级复现。
- `/align_to_apriltag`、`/wait_for_tag_removed`、`/door_traverse` 三个自定义 action 均可成功返回。
- `mission.launch.py` 可启动 perception、三个行为 server 和 `tour_deliberation_node`，并能按 landmarks 调用 Nav2/action。
- 若要自动完成完整 tour，Gazebo world 必须具备与 `landmarks.yaml` 匹配的可见 AprilTag 和可通行地图；当前仓库 world 还未满足这一点，因此自动 tour 的最后一步依赖场景资产补齐。

# 06 快速参考手册

> 适用对象：跑过一次仿真之后，想用一页纸把常用命令、接口、参数全部速查
> 用法：建议浏览器标签固定，随用随翻

---

## 1.目录速跳

- [1.目录速跳](#1目录速跳)
- [2.Docker Compose 命令](#2docker-compose-命令)
- [3.Launch 文件总览](#3launch-文件总览)
- [4.ROS 节点速查](#4ros-节点速查)
- [5.Topic 速查](#5topic-速查)
- [6.Action 速查](#6action-速查)
- [7.参数速查](#7参数速查)
- [8.Landmark 与方向枚举](#8landmark-与方向枚举)
- [9.AprilTag 配置](#9apriltag-配置)
- [10.常用 ros2 CLI](#10常用-ros2-cli)
- [11.故障速查](#11故障速查)
- [12.关键文件路径](#12关键文件路径)

---

## 2.Docker Compose 命令

设环境变量简化：

```bash
export DC='docker compose -f docker_stuff/compose.yaml'
```

| 场景 | 命令 |
|---|---|
| 构建镜像 | `$DC build dev` |
| 构建 ROS 工作空间 | `$DC run --rm build` |
| 启动仿真（含 Gazebo + Nav2 + RViz） | `$DC --profile sim up sim` |
| 启动真机/导航栈 | `$DC --profile robot up robot` |
| 启动任务 + 行为 | `$DC --profile mission up mission` |
| 开发 shell | `$DC run --rm --no-deps dev bash` |
| 查看状态 | `$DC ps --all` |
| 看日志（最后 200 行） | `$DC logs --tail=200 sim` |
| 停止全部 | `$DC down` |
| 强制重建并启动 | `$DC --profile sim up -d --force-recreate sim` |

---

## 3.Launch 文件总览

| Launch | 包 | 作用 |
|---|---|---|
| `sim.launch.py` | `tourbot_bringup` | 完整仿真：Gazebo + bridge + localization + Nav2 + RViz + 胶水节点 |
| `robot.launch.py` | `tourbot_bringup` | localization + Nav2 + RViz（不含 Gazebo） |
| `mission.launch.py` | `tourbot_bringup` | apriltag pipeline + 3 个行为 server + tour_deliberation |
| `apriltag_pipeline.launch.py` | `tourbot_perception` | 启动 `apriltag_node`，订阅相机，发布 `/detections` |
| `align_to_apriltag.launch.py` | `tourbot_behaviors` | 单独启对齐 server |
| `door_behavior.launch.py` | `tourbot_behaviors` | 含已知未实现节点，不推荐主路径使用 |

`sim.launch.py` 参数：

| 参数 | 默认 | 说明 |
|---|---|---|
| `use_custom_sim` | `false` | true 时用本仓库自定义 world/map |
| `custom_world` | `.../worlds/cardboard_city/world` | **不带 .sdf 后缀** |
| `custom_map` | `.../maps/cardboard_city/map_area.yaml` | Nav2 静态 map |

---

## 4.ROS 节点速查

完整 sim + mission 起来后预期可见的节点（按层分组）：

| 层 | 节点 | 包 |
|---|---|---|
| Gazebo | `gz sim`、`ros_gz_bridge` | turtlebot4_gz_bringup |
| 控制 | `controller_manager`、`diffdrive_controller`、`joint_state_broadcaster` | gz_ros2_control |
| 定位 | `amcl`、`map_server`、`lifecycle_manager_localization` | nav2 |
| 导航 | `planner_server`、`controller_server`、`bt_navigator`、`behavior_server`、`waypoint_follower`、`velocity_smoother`、`lifecycle_manager_navigation` | nav2 |
| 胶水 | `odom_tf_compat`、`nav2_post_localization_activator` | tourbot_bringup |
| 感知 | `apriltag` | apriltag_ros |
| 行为 | `align_to_apriltag_server`、`wait_for_tag_removed_server`、`door_behavior_server` | tourbot_behaviors |
| 任务 | `tour_deliberation_node` | tourbot_mission |

查询命令：

```bash
ros2 node list
ros2 node info /tour_deliberation_node
```

---

## 5.Topic 速查

| Topic | 类型 | 方向 | 说明 |
|---|---|---|---|
| `/scan` | `sensor_msgs/LaserScan` | 仿真→Nav2 | 激光雷达数据 |
| `/odom` | `nav_msgs/Odometry` | 仿真→TF→Nav2 | 里程计 |
| `/tf`、`/tf_static` | `tf2_msgs/TFMessage` | 多方 | 坐标系树 |
| `/map` | `nav_msgs/OccupancyGrid` | map_server→所有 | 静态地图 |
| `/initialpose` | `geometry_msgs/PoseWithCovarianceStamped` | RViz / mission→amcl | 初始位姿 |
| `/cmd_vel` | **`geometry_msgs/TwistStamped`** | controllers/行为→仿真 | 速度命令（注意是 Stamped） |
| `/oakd/rgb/preview/image_raw` | `sensor_msgs/Image` | 仿真→apriltag | 相机图像 |
| `/oakd/rgb/preview/camera_info` | `sensor_msgs/CameraInfo` | 仿真→apriltag/align | 相机内参 |
| `/detections` | `apriltag_msgs/AprilTagDetectionArray` | apriltag→行为 | 检测结果 |

调试：

```bash
ros2 topic list -t
ros2 topic hz /scan
ros2 topic echo /detections --once
```

---

## 6.Action 速查

### 6.1 自带 / Nav2

```text
/navigate_to_pose       nav2_msgs/action/NavigateToPose
```

发个目标：

```bash
ros2 action send_goal /navigate_to_pose nav2_msgs/action/NavigateToPose \
  "{pose: {header: {frame_id: 'map'}, pose: {position: {x: 0.5, y: 0.0, z: 0.0}, orientation: {w: 1.0}}}}" \
  --feedback
```

### 6.2 自研

**`/align_to_apriltag`** — 旋转对准 tag

```text
Goal:     int32 tag_id, float32 timeout_sec, float32 x_tolerance_px
Feedback: float32 x_error_px, bool tag_visible, string state
Result:   bool success, string message
```

```bash
ros2 action send_goal /align_to_apriltag \
  tourbot_interfaces/action/AlignToAprilTag \
  '{tag_id: 3, timeout_sec: 30.0, x_tolerance_px: 7.0}' --feedback
```

**`/wait_for_tag_removed`** — 等指定 tag 从视野消失

```text
Goal:     int32 tag_id, float32 timeout_sec, float32 missing_duration_sec
Feedback: bool tag_visible, float32 missing_time_sec, string state
Result:   bool success, string message
```

```bash
ros2 action send_goal /wait_for_tag_removed \
  tourbot_interfaces/action/WaitForTagRemoved \
  '{tag_id: 1, timeout_sec: 60.0, missing_duration_sec: 3.0}' --feedback
```

**`/door_traverse`** — 门穿越（先后退/转身/前进）

```text
Goal:     int32 tag_id
          float32 backup_distance, backup_speed
          float32 wait_seconds
          float32 forward_distance, forward_speed
Feedback: string current_state, float32 distance_traveled
Result:   bool success, string message
```

```bash
ros2 action send_goal /door_traverse \
  tourbot_interfaces/action/DoorTraverse \
  '{tag_id: 1, backup_distance: 0.0, backup_speed: 0.0, wait_seconds: 1.0, forward_distance: 0.3, forward_speed: 0.08}' --feedback
```

**`/do_landmark_task`** — 接口已定义，**当前未实现**

```text
Goal:     int32 waypoint_index, string expected_landmark_name, int32 expected_tag_id
```

---

## 7.参数速查

### 7.1 对齐行为（align_to_apriltag_server.py）

| 常量 | 默认 | 含义 |
|---|---|---|
| `SEARCH_ANGULAR_SPEED` | `0.20` | tag 找不到时的旋转速度（rad/s） |
| `ALIGN_KP` | `0.003` | 像素误差 → 角速度 P 增益 |
| `MAX_ANGULAR_SPEED` | `0.30` | 角速度上限 |

ROS 参数：

```text
detections_topic        默认 /detections
camera_info_topic       默认 /oakd/rgb/preview/camera_info
cmd_vel_topic           默认 /cmd_vel
```

### 7.2 门穿越行为（door_behavior_server.py）

| 参数 | 默认 |
|---|---|
| `backup_distance_default` | `0.9` |
| `backup_speed_default` | `0.15` |
| `wait_seconds_default` | `3.0` |
| `forward_distance_default` | `1.5` |
| `forward_speed_default` | `0.18` |
| `control_rate_hz` | `20.0` |

### 7.3 等 tag 消失（wait_for_tag_removed_server.py）

```text
detections_topic        默认 /detections
control_rate_hz         默认 20.0
```

### 7.4 Mission 流程关键常量

`tour_deliberation_node.py` 中：

```text
align timeout                30.0 s
align x_tolerance_px         7.0
wait_for_tag timeout         60.0 s
wait_for_tag missing dur     3.0 s
initial pose 重发次数        10
```

---

## 8.Landmark 与方向枚举

`cardboard_city` 当前 landmarks：

| name | tag_id | x | y | theta | 说明 |
|---|---|---|---|---|---|
| home | 0 | 0.00 | 0.00 | NORTH | 起点 |
| door_outward | 1 | 3.14 | 0.00 | SOUTH | outward door |
| door_inward | 2 | 1.71 | 0.00 | NORTH | inward door |
| goal_3 | 3 | 0.942 | 0.495 | WEST | 普通 landmark |
| goal_4 | 4 | 1.33 | -0.20 | EAST | 普通 landmark |
| goal_5 | 5 | 3.36 | -0.20 | EAST | 普通 landmark |
| goal_6 | 6 | 2.34 | -0.647 | WEST | 普通 landmark |
| goal_7 | 7 | 2.35 | 0.673 | EAST | 普通 landmark |

方向枚举（度）：

```text
NORTH=0   NORTH_WEST=45   WEST=90    SOUTH_WEST=135
SOUTH=180 SOUTH_EAST=225  EAST=270   NORTH_EAST=315
```

---

## 9.AprilTag 配置

文件：`src/tourbot_perception/config/apriltags_36h11.yaml`

```text
family:        36h11
size:          0.162 m
max_hamming:   0
z_up:          true
```

Pipeline launch：`apriltag_pipeline.launch.py` 把 `apriltag_node` remap 到：

```text
image_rect   ← /oakd/rgb/preview/image_raw
camera_info  ← /oakd/rgb/preview/camera_info
```

---

## 10.常用 ros2 CLI

```bash
# 节点 / topic / action 列表
ros2 node list
ros2 node info /<node>
ros2 topic list -t
ros2 topic info /<topic>
ros2 topic hz /<topic>
ros2 topic echo /<topic> --once
ros2 action list -t
ros2 action info /<action>

# TF 调试
ros2 run tf2_ros tf2_echo map base_link
ros2 run tf2_tools view_frames        # 生成 frames.pdf

# 参数
ros2 param list /<node>
ros2 param get  /<node> <name>
ros2 param set  /<node> <name> <value>

# 发布 / 调用
ros2 topic pub  -r 10 /<topic> <type> '<yaml>'
ros2 action send_goal /<action> <type> '<yaml>' --feedback
ros2 service call /<srv>     <type> '<yaml>'

# Lifecycle
ros2 lifecycle get  /<node>
ros2 lifecycle set  /<node> activate
```

---

## 11.故障速查

| 现象 | 第一招 |
|---|---|
| RViz 显示 `Localization: inactive` | RViz 左下 `2D Pose Estimate` 大致点击机器人位置；看 `nav2_post_localization_activator` 日志 |
| `Nav2 Goal` 点了不动 | 看 `controller_server` 日志，是否大量 `older than current time, ... exceeds allowed timeout (0.5)` |
| `cmd_vel` 没反应 | 类型是否是 `TwistStamped`；`header.stamp` 是否新鲜 |
| Gazebo 启动后退出 | 看是否 `symbol lookup error` / `undefined symbol`；ABI 不匹配按 007 SOP §4.2 修复 |
| 首次启动 Gazebo 卡在 `Downloading model` | 等模型下载，或预热后 `compose restart sim` |
| TurboVNC 卡顿 | 容器命令前加 `vglrun -d :0`；`nvidia-smi pmon` 看是否有 `gz sim`、`rviz2` |
| 行为 server 找不到 | 是否 `colcon build` 过，是否 `source install/setup.bash` |
| AprilTag 不出 `/detections` | `ros2 topic hz /oakd/rgb/preview/image_raw` 是否 > 0；camera_info 是否齐 |

---

## 12.关键文件路径

```text
src/tourbot_bringup/launch/
  ├── sim.launch.py
  ├── robot.launch.py
  └── mission.launch.py

src/tourbot_bringup/config/nav2_params.yaml
src/tourbot_bringup/maps/cardboard_city/map_area.{pgm,yaml}
src/tourbot_bringup/worlds/cardboard_city/world.sdf
src/tourbot_bringup/tourbot_bringup/
  ├── odom_tf_compat.py
  └── nav2_post_localization_activator.py

src/tourbot_mission/tourbot_mission/tour_deliberation_node.py
src/tourbot_landmarks/config/<map>/landmarks.yaml
src/tourbot_landmarks/tourbot_landmarks/landmarks_loader.py

src/tourbot_behaviors/tourbot_behaviors/
  ├── align_to_apriltag_server.py
  ├── wait_for_tag_removed_server.py
  └── door_behavior_server.py

src/tourbot_perception/launch/apriltag_pipeline.launch.py
src/tourbot_perception/config/apriltags_36h11.yaml

src/tourbot_interfaces/action/
  ├── AlignToAprilTag.action
  ├── WaitForTagRemoved.action
  ├── DoorTraverse.action
  └── DoLandmarkTask.action

docker_stuff/compose.yaml
docker_stuff/Dockerfile.jazzy
docker_stuff/ros_entrypoint.sh
```

---

## 13.一行总结

> 把 `landmarks.yaml` 当成 **剧本**，Nav2 是 **腿**，AprilTag pipeline 是 **眼**，行为 server 是 **手**，`tour_deliberation_node` 是 **大脑**——大脑按剧本调用腿和手，眼负责确认位置。

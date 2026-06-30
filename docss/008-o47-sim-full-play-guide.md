# Tour Guide Robot 完整玩法指南（从初级到高级）

> 编写日期：2026-06-30
> 目标主机：`xiao-5080` / `5080-MS-eSport-Z890M` / Ubuntu 24.04
> 目标仓库：`/home/xiaozy/4sim/gh-ref/tour-guide-robot/Hyaxon-tour-guide-robot`
> 操作原则：所有命令都在 `xiao-5080` 上执行，不在当前 Dell notebook 上改仓库内容。
> 适用场景：从第一次接触本仓库的工程师，到打算扩展场景资产、定制 mission、深度改造行为逻辑的研发人员。

---

## 0. 总览：本仓库到底能玩什么

本仓库是一个基于 ROS 2 Jazzy + TurtleBot4 的室内导游机器人原型。所有能力都已经在 9 个 ROS 包里：

| 包 | 提供能力 |
|---|---|
| `tourbot_bringup` | Gazebo 仿真 / 真机 / mission 三套 launch，含 cardboard_city map 和 world 框架 |
| `tourbot_landmarks` | landmark YAML 配置（pose + tag_id + 朝向） |
| `tourbot_mission` | `tour_deliberation_node`，最近邻 landmark 巡游 |
| `tourbot_behaviors` | `/align_to_apriltag`、`/wait_for_tag_removed`、`/door_traverse` 三个 action server |
| `tourbot_perception` | AprilTag 36h11 检测管线，发布 `/detections` |
| `tourbot_interfaces` | 4 个自定义 action 接口 |
| `apriltag*` | 第三方 AprilTag 库 |

按照学习曲线，本仓库的玩法可以分成 5 个层级：

```
L1 入门  → 起容器、起仿真、看 RViz/Gazebo
L2 基础  → Nav2 单点导航 + RViz 手动控制
L3 进阶  → 调用三个自定义 action（对齐、等门、穿门）做行为级验证
L4 高级  → 完整 mission 自动巡游 + AprilTag perception 闭环
L5 专家  → 改 landmark / 改 world / 加场景资产 / 接真机 / 改 behavior 算法
```

每一层都对应一组明确的命令、可观察现象、典型踩坑。下面分级展开。

---

## L1 入门：把项目跑起来，看到画面

### L1.1 目标

- 远端环境 OK：VNC + GPU + Docker + Compose 都能用。
- 镜像和工作空间能构建。
- Gazebo + RViz2 + TurtleBot4 HMI 三个窗口在 VNC 桌面里可见。

### L1.2 远端入口

```bash
ssh xiao-5080
cd /home/xiaozy/4sim/gh-ref/tour-guide-robot/Hyaxon-tour-guide-robot
export DC='docker compose -f docker_stuff/compose.yaml'
```

确认主机：

```bash
hostname     # 期望: 5080-MS-eSport-Z890M
pwd          # 期望: /home/xiaozy/4sim/gh-ref/tour-guide-robot/Hyaxon-tour-guide-robot
git branch --show-current   # 期望: x5080
```

### L1.3 接入 TurboVNC

Dell notebook 上建 tunnel：

```bash
ssh -N -L 5922:127.0.0.1:5922 xiao-5080
/opt/TurboVNC/bin/vncviewer localhost::5922
```

如果远端 VNC 未启动：

```bash
~/scripts/start-turbovnc-vnc22.sh
```

容器默认使用：

```text
DISPLAY=:22
XAUTHORITY=/home/xiaozy/.Xauthority
VGL_DISPLAY=:0   # GUI 通过 VirtualGL 转到物理 Xorg :0 走 RTX 5080
```

### L1.4 构建镜像和工作空间

```bash
$DC build dev
$DC run --rm build
```

预期输出：`Summary: 9 packages finished`。

可选：在不污染命名卷的临时路径快速验证可重建：

```bash
$DC run --rm --no-deps dev bash -lc '
  source /opt/ros/jazzy/setup.bash &&
  colcon --log-base /tmp/tourbot-log build \
    --symlink-install \
    --build-base /tmp/tourbot-build \
    --install-base /tmp/tourbot-install'
```

### L1.5 第一次启动：官方 warehouse 仿真

最容易看到画面的入口，不依赖本仓库的 cardboard_city world：

```bash
ROS_DOMAIN_ID=142 $DC --profile sim up sim
```

这条命令背后做的事：

- 容器内执行 `vglrun -d :0 ros2 launch tourbot_bringup sim.launch.py`
- `use_custom_sim` 默认 `false`，走 TurtleBot4 官方 warehouse world
- 同时拉起 Gazebo Harmonic、TurtleBot4 spawn、ros-gz bridge、localization、Nav2、RViz2

VNC 桌面里应能看到 3 个窗口：Gazebo（带 TurtleBot4 模型）、RViz2（带 navigation 面板）、TurtleBot4 HMI 插件。

首次启动会从 Gazebo Fuel 下载场景模型，日志里持续出现 `Downloading model [fuel.gazebosim.org/...]`。等下载完毕、controller 起来后重启一次即可。

### L1.6 L1 验收

- `nvidia-smi pmon -c 1` 看到 `gz sim server`、`gz sim gui`、`rviz2` 在 GPU 图形进程里。
- `$DC exec sim bash -lc 'ros2 topic list'` 看到 `/odom`、`/scan`、`/tf`、`/clock`、`/map`、`/oakd/rgb/preview/image_raw` 等。
- RViz2 中 `Fixed Frame: map`，能看到 occupancy grid 和 TurtleBot4 模型轮廓。

---

## L2 基础：让机器人走起来

### L2.1 目标

- 理解 Nav2 lifecycle 节点的 active / inactive 状态。
- 在 RViz2 里设置初始位姿。
- 用 RViz2 `Nav2 Goal` 或 CLI 发一个点到点目标，看到机器人在 Gazebo 里同步移动。

### L2.2 让 localization / Nav2 进入 active

刚启动的 `sim.launch.py` 里，已经做过一次 lifecycle activator 改造（见 commit `be64ad5`）：先起 Gazebo/控制器，30 秒后再起 localization/Nav2/RViz；同时 `nav2_post_localization_activator` 会在 AMCL 产出 `map -> base_link` 后自动激活 Nav2。

如果 RViz2 左下角 Navigation 2 面板显示：

```text
Navigation: inactive
Localization: inactive
```

按下列顺序处理：

1. 在 RViz2 工具栏点 `2D Pose Estimate`，在地图上对应机器人当前位置点击并拖动方向，发布到 `/initialpose`。
2. 等待 AMCL 收敛，`map -> odom -> base_link` TF 链应当出现。
3. 此时 activator 会逐个把 `amcl`、`bt_navigator`、`controller_server`、`planner_server`、`behavior_server`、`waypoint_follower`、`velocity_smoother` configure -> activate。
4. Navigation 2 面板变成 `Localization: active` / `Navigation: active`。

手动检查：

```bash
$DC exec sim bash -lc '
  source install/setup.bash &&
  ros2 run tf2_ros tf2_echo map base_link
'
```

应该能持续打印当前位姿。

### L2.3 发第一个 Nav2 目标

#### RViz2 方式

点工具栏 `Nav2 Goal`，在地图可通行区域点击并拖动方向。Navigation 2 面板会显示 ETA / 剩余距离，RViz2 中能看到 global plan / local plan。

#### CLI 方式

```bash
$DC exec sim bash -lc '
  source install/setup.bash &&
  ros2 action send_goal /navigate_to_pose nav2_msgs/action/NavigateToPose \
    "{pose: {header: {frame_id: \"map\"}, pose: {position: {x: 0.5, y: 0.0, z: 0.0}, orientation: {w: 1.0}}}}" \
    --feedback
'
```

### L2.4 常见“看似不动”的现象

参考 `docss/009-ui-operate-guide-ts.md` 第 9 节的实测结论：日志里 `Goal succeeded`、Gazebo ground truth 也已经到目标附近，但视觉上感觉机器人停顿。常见原因：

- Gazebo diffdrive_controller 拒收旧时间戳速度命令：`older than the current time ... exceeds allowed timeout (0.5000)`。
- Nav2 中途 `Failed to make progress`，触发 recovery、清 costmap、重新跟踪路径。
- `/odom`、RViz `map` 位姿、Gazebo warehouse ground truth 不是同一坐标源；要看真正物理位置请订阅 `/_internal/sim_ground_truth_pose`。

### L2.5 用 TurtleBot4 HMI 做手动控制

Gazebo 窗口右侧的 TurtleBot4 HMI（来自 `turtlebot4_gz_bringup` 的 GUI 插件）支持：

```text
Dock / Undock / EStop / Wall Follow / Teleop
```

注意：HMI 是给 TurtleBot4 行为命令的入口，不是发地图目标的入口。地图点到点导航必须走 RViz2 `Nav2 Goal` 或 `/navigate_to_pose`。

### L2.6 L2 验收

- AMCL 已收敛，`map -> base_link` 持续存在。
- Nav2 7 个 lifecycle 节点全部 active。
- 至少一次 `Nav2 Goal` 成功，机器人在 Gazebo 中可见地移动到目标点。
- HMI 中 `Teleop` 可以小范围控车。

---

## L3 进阶：调用三个自定义 action 做行为级验证

### L3.1 目标

在还没有完整 AprilTag 场景资产时，通过 `ros2 topic pub` 注入合成的 `/detections`，单独验证：

- `/align_to_apriltag`：对齐到指定 tag。
- `/wait_for_tag_removed`：等待 tag 消失（模拟开门）。
- `/door_traverse`：staged 门穿越。

### L3.2 启动 perception + behavior + mission

进入和 `sim` 同 ROS domain 的开发容器：

```bash
$DC run --rm --no-deps dev bash
source install/setup.bash
```

启动 mission graph（不启动 GUI）：

```bash
ros2 launch tourbot_bringup mission.launch.py
```

`mission.launch.py` 启动顺序固定：

1. `apriltag_pipeline.launch.py`
2. 2.0s 后 `align_to_apriltag_server`
3. 2.5s 后 `wait_for_tag_removed_server`
4. 3.0s 后 `door_behavior_server`
5. 10.0s 后 `tour_deliberation_node`

如果想单独玩某个 action server，跳过 mission node：

```bash
ros2 run tourbot_behaviors align_to_apriltag_server
ros2 run tourbot_behaviors wait_for_tag_removed_server
ros2 run tourbot_behaviors door_behavior_server
```

### L3.3 `/align_to_apriltag` 玩法

接口：

```text
action: /align_to_apriltag [tourbot_interfaces/action/AlignToAprilTag]
sub:    /detections, /oakd/rgb/preview/camera_info
pub:    /cmd_vel (TwistStamped)
```

终端 A，持续发相机信息：

```bash
ros2 topic pub -r 10 /oakd/rgb/preview/camera_info sensor_msgs/msg/CameraInfo \
  '{width: 640, height: 480}'
```

终端 B，发布一个已居中的 tag 3 detection：

```bash
ros2 topic pub -r 10 /detections apriltag_msgs/msg/AprilTagDetectionArray \
  "{detections: [{family: '36h11', id: 3, hamming: 0, goodness: 1.0,
    decision_margin: 100.0, centre: {x: 320.0, y: 240.0},
    corners: [{x: 300.0, y: 220.0}, {x: 340.0, y: 220.0}, {x: 340.0, y: 260.0}, {x: 300.0, y: 260.0}],
    homography: [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0],
    header: {frame_id: 'oakd_rgb_camera_optical_frame'}}]}"
```

终端 C，发 goal：

```bash
ros2 action send_goal /align_to_apriltag \
  tourbot_interfaces/action/AlignToAprilTag \
  '{tag_id: 3, timeout_sec: 5.0, x_tolerance_px: 7.0}' \
  --feedback
```

观察：

| 输入条件 | 期望行为 |
|---|---|
| tag 居中 | result `success: true`，message 类似 `Aligned to tag 3.` |
| tag 不存在 | 以 `SEARCH_ANGULAR_SPEED=0.20` 持续旋转，直到 timeout |
| tag 偏左/偏右 | 按 `ALIGN_KP=0.003` 计算角速度，限幅 `MAX_ANGULAR_SPEED=0.30` |

### L3.4 `/wait_for_tag_removed` 玩法

模拟“门一开 tag 就消失”：

终端 A，先发空 detection：

```bash
ros2 topic pub -r 10 /detections apriltag_msgs/msg/AprilTagDetectionArray '{detections: []}'
```

终端 B，发 goal：

```bash
ros2 action send_goal /wait_for_tag_removed \
  tourbot_interfaces/action/WaitForTagRemoved \
  '{tag_id: 1, timeout_sec: 10.0, missing_duration_sec: 2.0}' \
  --feedback
```

期望 2 秒后 result `success: true`。

模拟“先看到 tag 再消失”更接近真实：

1. 先以 10 Hz 发 tag 1 detection。
2. 发 `/wait_for_tag_removed` goal。
3. 停 tag 1 publisher，改发 `{detections: []}`。
4. 等待 `missing_duration_sec` 后 action 返回成功。

### L3.5 `/door_traverse` 玩法

只在仿真或安全隔离机器人上执行，会发 `/cmd_vel`。

确认 odom 有数据：

```bash
ros2 topic echo /odom --once
```

outward door 小距离测试（tag_id=1）：

```bash
ros2 action send_goal /door_traverse \
  tourbot_interfaces/action/DoorTraverse \
  '{tag_id: 1, backup_distance: 0.0, backup_speed: 0.0,
    wait_seconds: 1.0, forward_distance: 0.2, forward_speed: 0.05}' \
  --feedback
```

inward door 小距离测试（tag_id=2）：

```bash
ros2 action send_goal /door_traverse \
  tourbot_interfaces/action/DoorTraverse \
  '{tag_id: 2, backup_distance: 0.2, backup_speed: 0.05,
    wait_seconds: 1.0, forward_distance: 0.2, forward_speed: 0.05}' \
  --feedback
```

代码默认参数（参考 `door_behavior_server`）：

```text
backup_distance_default: 0.9
backup_speed_default:    0.15
wait_seconds_default:    3.0
forward_distance_default:1.5
forward_speed_default:   0.18
control_rate_hz:         20.0 (代码默认) / 10.0 (door_behavior.yaml)
```

⚠️ 已知问题：`door_behavior.launch.py` 引用了不存在的 `manual_door_override_node`，不要用这个 launch；用 `ros2 run` 或 `mission.launch.py` 起 server 才稳。

### L3.6 L3 验收

- 三个 action 都能用合成 `/detections` 成功返回。
- `/cmd_vel` 输出符合预期（旋转 / 前进 / 后退）。
- 没有 ROS graph 重复节点告警。

---

## L4 高级：完整 mission 自动巡游

### L4.1 目标

让 `tour_deliberation_node` 自动按 landmark 列表巡游：

1. 把 `home` 作为初始位姿，连发 10 次 initial pose。
2. 等 Nav2 active。
3. 对 landmarks 做最近邻贪心排序。
4. 每个 landmark：`Nav2 startToPose()` -> `/align_to_apriltag` -> 门处理或 180° 离开。
5. 全部完成后回 home。

### L4.2 当前 landmark 配置

`tourbot_landmarks/config/cardboard_city/landmarks.yaml`：

```text
home          tag_id=0   (0, 0)         NORTH
door_outward  tag_id=1   (3.14, 0)      SOUTH    -> outward 门规则
door_inward   tag_id=2   (1.71, 0)      NORTH    -> inward 门规则
goal_3        tag_id=3   (0.942, 0.495) WEST
goal_4        tag_id=4   (1.33, -0.2)   EAST
goal_5        tag_id=5   (3.36, -0.2)   EAST
goal_6        tag_id=6   (2.34, -0.647) WEST
goal_7        tag_id=7   (2.35, 0.673)  EAST
```

门规则在 mission 代码里固定：

- tag_id=1：outward door，等 tag 消失后直接前进穿越。
- tag_id=2：inward door，先转身/后退/再转回，然后前进。
- 其它：对齐后旋转 180° 离开。

### L4.3 两段式启动（仿真之外的方式）

如果不用集成 `sim` profile，而是按 README 的两段式：

终端 A：

```bash
$DC --profile robot up robot   # 启动 robot.launch.py: 仅 localization+Nav2+RViz
```

终端 B：

```bash
$DC --profile mission up mission   # 启动 perception+behavior+mission
```

注意：默认 `ROS_DOMAIN_ID=42`。不要同时跑 `sim` 内置的 Nav2 和 `robot.launch.py` 的第二套 Nav2，会出现重复节点；smoke test 时只跑一种栈，或用不同 DOMAIN_ID 隔离。

### L4.4 用集成 sim 跑 mission

更简单的路径：先用 `sim` 把仿真+导航起好，然后在同 ROS domain 内启动 mission：

```bash
ROS_DOMAIN_ID=142 $DC --profile sim up -d --force-recreate sim
ROS_DOMAIN_ID=142 $DC --profile mission up -d --force-recreate mission
```

`tour_deliberation_node` 会自动开始：

```bash
$DC logs --tail=160 mission | grep -E 'tour_deliberation|navigate_to_pose|align_to_apriltag|wait_for_tag_removed|door_traverse'
```

### L4.5 完整 mission 自动跑通的前提

- Nav2 已 active，`/map`、`/scan`、`/odom`、`/tf` 正常。
- `/oakd/rgb/preview/image_raw` 和 `/oakd/rgb/preview/camera_info` 有数据。
- AprilTag pipeline 能在 landmark 附近发布对应 tag 到 `/detections`。
- 门 tag 1/2 能先可见、再消失至少 3 秒。
- `/cmd_vel` 控制的是仿真机器人或安全隔离机器人。

如果当前 cardboard_city world 没放真实 tag 模型，mission 会在对齐阶段持续搜索直到 timeout——这不是 server 故障，而是场景资产缺失（L5 解决）。

### L4.6 关键 topic / action / 节点速查

action：

```text
/align_to_apriltag      tourbot_interfaces/action/AlignToAprilTag
/door_traverse          tourbot_interfaces/action/DoorTraverse
/navigate_to_pose       nav2_msgs/action/NavigateToPose
/wait_for_tag_removed   tourbot_interfaces/action/WaitForTagRemoved
```

topic：

```text
/cmd_vel                geometry_msgs/msg/TwistStamped   # 注意是 Stamped!
/detections             apriltag_msgs/msg/AprilTagDetectionArray
/map                    nav_msgs/msg/OccupancyGrid
/oakd/rgb/preview/...   sensor_msgs/{Image,CameraInfo,Image(depth)}
/odom                   nav_msgs/msg/Odometry
/scan                   sensor_msgs/msg/LaserScan
/tf                     tf2_msgs/msg/TFMessage
```

期望节点列表：

```text
/amcl
/align_to_apriltag_server
/apriltag
/bt_navigator
/controller_server
/door_behavior_server
/planner_server
/tour_deliberation_node
/wait_for_tag_removed_server
```

### L4.7 L4 验收

- mission 启动后能看到 `tour_deliberation_node` 依次产出 `startToPose` 调用 + action 调用日志。
- 至少一次走到 landmark + 对齐 + 离开 的循环成功。
- 如果有完整 AprilTag 资产，能闭环跑完整张 landmark 列表回 home。

---

## L5 专家：扩展场景、定制 mission、改造 behavior 算法

到这一层就不再是“按 SOP 跑通”，而是把这个仓库当作可改造的脚手架。下面列出可独立或组合进行的玩法。

### L5.1 扩 Gazebo 场景资产

当前 `src/tourbot_bringup/worlds/cardboard_city/world.sdf` 只有地面、灯光、GUI、系统插件，没有墙体、门和 AprilTag。完整自动 tour 需要补：

- 墙体 / 门模型（可用 Gazebo Fuel cardboard box 资产或自建 SDF）。
- AprilTag 36h11 平面模型，把对应 `tag_id` 贴在 landmark 附近，朝向与 `landmarks.yaml` 的 `theta` 一致。
- 一个真实可控的“门 tag 消失”机制：常见做法是用 Gazebo 系统插件在某条件下移除 tag visual，或把 tag 模型挂在门板上、开门时 tag 旋转到相机视野外。

启动自定义 world 的正确命令（注意路径不要带 `.sdf`，下游 launch 会自动追加）：

```bash
$DC run --rm --no-deps dev bash -lc '
  source install/setup.bash
  ros2 launch tourbot_bringup sim.launch.py \
    use_custom_sim:=true \
    custom_world:=/ws/install/tourbot_bringup/share/tourbot_bringup/worlds/cardboard_city/world \
    custom_map:=/ws/install/tourbot_bringup/share/tourbot_bringup/maps/cardboard_city/map_area.yaml \
    rviz:=true
'
```

⚠️ `sim.launch.py` 默认 `custom_world` 写成 `cardboard_city.sdf`，但实际文件是 `world.sdf`。这是已知不匹配，启动时显式覆盖即可。

### L5.2 加新 landmark 或换地图

新增 landmark：

1. 编辑 `src/tourbot_landmarks/config/cardboard_city/landmarks.yaml`，加一行：

```yaml
- name: goal_8
  tag_id: 8
  x: 2.0
  y: 1.0
  theta: NORTH
```

2. 在 `apriltags_36h11.yaml` 中声明对应 tag id。
3. 在 world 中放置对应 tag 模型。
4. 重新 `colcon build --symlink-install`（symlink 时改 YAML 通常不需要重 build，但 install 路径下的 share 副本除外，按需 verify）。

换地图：

1. 在 `tourbot_bringup/maps/` 下新建目录，放 `map_area.pgm` + `map_area.yaml`。
2. 在 `tourbot_landmarks/config/` 下新建同名目录，写新的 `landmarks.yaml`。
3. 当前 `tour_deliberation_node` 固定加载 `cardboard_city`，要么改源码、要么把新地图也命名为 `cardboard_city`、要么把这个名字提成参数。

### L5.3 定制 mission 顺序

`tour_deliberation_node` 默认用最近邻贪心排序。可以改造：

- 改为按 YAML 顺序访问。
- 改为按 cluster / 楼层分组访问。
- 加入“访问优先级 / TTL”。
- 在每个 landmark 上插入额外行为（讲解音频、停留 X 秒、调用未来的 `DoLandmarkTask`）。

注意当前 `landmark_task_server.py` 只是 TODO 占位，`DoLandmarkTask.action` 也没接入 mission，是天然的扩展点。

### L5.4 改造 align / door behavior 算法

可改的地方：

- `align_to_apriltag_server`：
  - 搜索方向当前是固定方向，右侧 tag 检测较慢。可以接 IMU 或上一次成功方向做有向搜索。
  - `ALIGN_KP=0.003` 是固定 P 控制，可以加 D / I 或换基于 tag 像素 + tag size 的 PD。
- `wait_for_tag_removed_server`：当前用 visible/invisible 做二值门状态。可改为基于 LIDAR 或深度图判定门是否真的开了。
- `door_behavior_server`：当前是 odometry 开环 staged 行为，没有 servoing。可改为基于 LIDAR 的反应式穿越，或基于 tag 的 visual servoing。

每次改完用 L3 的合成 `/detections` 做单元级回归，避免直接上 mission。

### L5.5 接真机 TurtleBot4

参考 README 的 `robot.launch.py` 路径：

1. 真机配置 ROS_DOMAIN_ID 与本仓库容器一致。
2. 不启 `sim`，只启 `robot` + `mission` profile。
3. 检查真机相机话题命名是否就是 `/oakd/rgb/preview/image_raw`；如不同需要 remap 或改 `apriltag_pipeline.launch.py`。
4. `/cmd_vel` 是 `TwistStamped`，老脚本发 `Twist` 不会被消费。

接真机前必做：

- 在仿真里完整跑通 L4，确认 mission 节点都能正确进入和退出 align / door 状态。
- 把 `door_traverse` 默认参数缩小到安全距离再放大。
- 准备硬件 EStop。

### L5.6 接入更多感知 / 调试工具

- 用 `rqt_graph` 看节点 / topic 关系。
- 用 `ros2 bag record /odom /scan /cmd_vel /detections /tf /tf_static` 录数据回放调试。
- 用 PlotJuggler 监控 `/odom`、`/cmd_vel`、AMCL 协方差。
- 在 mission 节点里加结构化日志（status / step / landmark_id）。

### L5.7 镜像 / 容器层的高级玩法

- 修改 `docker_stuff/Dockerfile.jazzy`：
  - 已经显式锁定了一组 `ros-jazzy-rclcpp*` 和 `diagnostic-updater` 版本，避免 ABI 混用。
  - 已经预装 `virtualgl`，所有 GUI 通过 `vglrun -d :0` 走物理 Xorg。
- 修改 `docker_stuff/compose.yaml`：
  - 自定义 profile：可以加一个 `--profile dev-gpu` 专门跑 `nvidia-smi pmon` 监控。
  - 网络模式：当前 `network_mode: host`，多机协作时考虑分 DDS discovery。

### L5.8 L5 验收（任选一项）

- 在 cardboard_city world 里放置至少一个 AprilTag，让 mission 自动完成至少一次完整 landmark + align 循环。
- 替换 `tour_deliberation_node` 的最近邻策略为自定义策略，跑通 mission。
- 改造 `align_to_apriltag_server` 的搜索方向逻辑，并用 ros2 bag 数据验证改善。
- 在真机 TurtleBot4 上完成 home -> goal_3 -> home 的最小 tour。

---

## 附录 A：分级玩法速查表

| 层级 | 一句话目标 | 主要命令 | 关键验收 |
|---|---|---|---|
| L1 | 把仿真跑起来 | `$DC --profile sim up sim` | VNC 里看到 Gazebo + RViz2 + HMI |
| L2 | 走第一个 Nav2 目标 | RViz2 `2D Pose Estimate` + `Nav2 Goal` | 机器人在 Gazebo 中可见地移动 |
| L3 | 玩三个自定义 action | `ros2 action send_goal /align_to_apriltag ...` 等 | 三个 action 都成功返回 |
| L4 | 跑完整 mission | `$DC --profile mission up mission` | 自动巡游 landmark 列表 |
| L5 | 改造和扩展 | 改 YAML / world / behavior 源码 | 任选 L5.8 中一项 |

---

## 附录 B：常见踩坑速查

| 现象 | 原因 | 处理 |
|---|---|---|
| Gazebo 启动一会儿退出，日志 `undefined symbol: ... diagnostic_updater::Updater` | 旧镜像 ros-jazzy-rclcpp 与 controller_manager ABI 不匹配 | 重建镜像（Dockerfile.jazzy 已锁版本） |
| `glxinfo` 显示 `Mesa llvmpipe`，GUI 卡顿 | 没走 VirtualGL | 使用 `vglrun -d :0 ...` 或 `sim/robot` profile（已默认） |
| 发 `Twist` 到 `/cmd_vel` 没反应 | 接口是 `TwistStamped` | 改用 TwistStamped |
| RViz2 显示 `Navigation: inactive` | Nav2 lifecycle 未激活 | 先 `2D Pose Estimate`，等 activator 拉起 |
| mission 在对齐阶段不停旋转 | 场景里没真实 tag | 用合成 `/detections` 或补 world 资产 |
| 同时启 sim 和 robot 出现节点重复 | 两套 Nav2 / RViz | 只跑一种栈，或用不同 ROS_DOMAIN_ID |
| `ros2 launch tourbot_behaviors door_behavior.launch.py` 报错 | 引用了不存在的 `manual_door_override_node` | 改用 `ros2 run tourbot_behaviors door_behavior_server` |
| `sim.launch.py` 默认 `custom_world` 路径不对 | 默认写的是 `cardboard_city.sdf`，实际是 `world.sdf` | 启动时显式覆盖，路径不带 `.sdf` 后缀 |

---

## 附录 C：相关文档导航

- `docss/007-sim-full-funtion-sop.md`：本文 L1–L4 的底层 SOP，含 ABI 修复、VirtualGL 修复、Compose digest 验证等细节。
- `docss/009-ui-operate-guide.md` / `009-ui-operate-guide-ts.md`：RViz2 / Gazebo / HMI 现场操作和“目标已到但看似不动”的排查记录。
- `docss/006-docker-compose-bp.md`：Compose / Dockerfile 最佳实践。
- `docss/101-*-turbovnc-low-framerate-ts.md`、`102-xiaozy-turbovnc-bp.md`：TurboVNC 帧率和远端桌面相关。
- 仓库 `README.md`：功能概览、第三方依赖、license。

---

## 附录 D：本文档的玩法约定

- 命令均默认在远端 `xiao-5080` 上、仓库根目录执行。
- 所有 GUI 都走 `DISPLAY=:22` + VNC，OpenGL 通过 `vglrun -d :0` 转到物理 Xorg。
- `$DC` 是 `docker compose -f docker_stuff/compose.yaml` 的别名，本文档默认已 `export DC=...`。
- 章节之间是“可以但非必须”的累进关系：L1 是入口，L2–L4 是渐进验收，L5 是发散方向。

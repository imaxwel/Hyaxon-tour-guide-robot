# Tour Guide Robot 仿真玩法指南：从初级到高级

> 编写日期：2026-06-30  
> 目标主机：`xiao-5080` / `5080-MS-eSport-Z890M` / Ubuntu 24.04  
> 目标仓库：`/home/xiaozy/4sim/gh-ref/tour-guide-robot/Hyaxon-tour-guide-robot`  
> 操作原则：所有命令都在 `xiao-5080` 上执行，不在 MacBook Pro 本机执行。  
> 本文定位：`007-sim-full-funtion-sop.md` 解决怎么完整复现已有功能；本文解决基于这个工程可以怎么玩、怎么逐级扩展。

---

## 0. 使用前提

先进入远端仓库：

```bash
ssh xiao-5080
cd /home/xiaozy/4sim/gh-ref/tour-guide-robot/Hyaxon-tour-guide-robot
```

推荐给 Compose 命令设置一个短变量：

```bash
export DC='docker compose -f docker_stuff/compose.yaml'
```

当前推荐基线运行态：

```bash
$DC --profile robot --profile mission stop robot mission
$DC --profile sim up -d --force-recreate sim
```

说明：

- `sim` 已包含 Gazebo、TurtleBot4、bridge、localization、Nav2、RViz，适合作为仿真主入口。
- `robot` 会再启动一套 localization/Nav2/RViz；做 smoke test 时不要和 `sim` 同时跑，避免同一 `ROS_DOMAIN_ID=42` 下出现重复 graph。
- `mission` 会启动 AprilTag perception、三个行为 action server 和 `tour_deliberation_node`；需要测完整任务时再启动。
- GUI 已通过 `vglrun -d :0` 走 RTX 5080；若 Gazebo/RViz 又变卡，先按 007 的 VirtualGL 检查流程确认 OpenGL renderer。

进入已经运行的 `sim` 容器执行 ROS 命令：

```bash
$DC exec sim bash
cd /ws
source install/setup.bash
```

从一次性开发容器执行 ROS 命令：

```bash
$DC run --rm --no-deps dev bash
cd /ws
source install/setup.bash
```

---

## 1. 玩法总览

| 等级 | 玩法 | 目标 | 推荐入口 | 验收点 |
|---|---|---|---|---|
| L0 | 基线观光 | 看见 Gazebo warehouse、RViz、机器人和传感器 | `--profile sim` | GUI 出图、`/clock`、`/odom`、`/scan` 正常 |
| L1 | ROS graph 探险 | 熟悉节点、topic、service、action、TF | `ros2 topic/node/action` | 能解释数据从 Gazebo 到 Nav2/RViz 的路径 |
| L2 | 手动驾驶 | 直接发 `/cmd_vel` 操控 TurtleBot4 | `TwistStamped` topic pub | 机器人能低速前进、旋转、停止 |
| L3 | Nav2 点到点导航 | 用 RViz 或 CLI 发送目标点 | `/navigate_to_pose` | 能规划、避障、到点、恢复 |
| L4 | 传感器可视化 | 看 LiDAR、RGB、depth、point cloud | RViz + topic hz | 图像、深度、点云、scan 有稳定频率 |
| L5 | AprilTag 感知 | 调试 `/detections` 和 tag TF | `apriltag_pipeline` | 有 tag 时能发布 detection 和 TF |
| L6 | 单行为 action | 直接调用对齐、等门、穿门 action | `ros2 action send_goal` | action feedback/result 符合预期 |
| L7 | 完整 tour mission | 让 mission 节点串起 Nav2 + behavior | `--profile mission` | 能按 landmarks 顺序运行，失败点可定位 |
| L8 | 改 landmarks | 自定义讲解点、门点、路线顺序 | `landmarks.yaml` | mission 读取新点位并改变路线 |
| L9 | 改 world/map | 补 cardboard city、门、AprilTag 模型 | `world.sdf` + map YAML | 仿真场景和 landmarks 对齐 |
| L10 | 行为调参 | 调整对齐、门穿越、超时、速度 | Python/YAML/launch 参数 | 行为更稳定、更少超时 |
| L11 | Mission planner 升级 | 从贪心路线升级到策略/BT/任务编排 | `tour_deliberation_node.py` | 可恢复、可跳过、可重试、可解释 |
| L12 | 数据与回归 | 录 bag、跑指标、复现失败场景 | `ros2 bag` + smoke scripts | 每次改动有可比较结果 |
| L13 | 多机器人/真机衔接 | domain、namespace、仿真到真机 | ROS_DOMAIN_ID/namespace | 仿真和真实机器人互不干扰 |
| L14 | 智能讲解员 | 接入语音、LLM/VLM、多模态交互 | mission 扩展节点 | 机器人能边导航边讲解和应答 |

建议顺序：先 L0-L3 建立手感，再做 L4-L7 验证已有机器人能力，最后从 L8 开始把项目变成真正可演示、可研究、可迭代的 tour guide robot。

---

## 2. L0：基线观光

目标：确认仿真环境、GUI、GPU、ROS graph 没问题。

启动：

```bash
$DC --profile robot --profile mission stop robot mission
$DC --profile sim up -d --force-recreate sim
$DC logs --tail=120 sim
```

检查 GUI 是否走 GPU：

```bash
$DC exec -T sim bash -lc '
  cd /ws && source install/setup.bash
  DISPLAY=:22 XAUTHORITY=/home/xiaozy/.Xauthority vglrun -d :0 glxinfo -B | grep -E "OpenGL renderer|direct rendering"
'

nvidia-smi pmon -c 1 | egrep 'gz|rviz|#'
```

检查基础 ROS topic：

```bash
$DC exec -T sim bash -lc '
  cd /ws && source install/setup.bash
  ros2 topic list | egrep "^/(clock|map|odom|scan|tf)$|^/oakd/rgb/preview"
'
```

验收标准：

- VNC 桌面能看到 Gazebo warehouse 和 RViz。
- `OpenGL renderer` 是 `NVIDIA GeForce RTX 5080/PCIe/SSE2`。
- `/clock`、`/map`、`/odom`、`/scan`、`/tf` 和 `/oakd/rgb/preview/*` 可见。
- `sim` 日志没有 `undefined symbol`、`symbol lookup error`、`process has died`。

---

## 3. L1：ROS Graph 探险

目标：把这个工程看成一个可观察系统，知道每个模块发布和消费什么。

进入 `sim` 容器：

```bash
$DC exec sim bash
cd /ws
source install/setup.bash
```

常用观察命令：

```bash
ros2 node list
ros2 topic list
ros2 service list | sort
ros2 action list | sort
ros2 topic hz /scan
ros2 topic echo --once /odom
ros2 run tf2_ros tf2_echo map base_link
```

建议重点理解这些链路：

- Gazebo -> `/clock`：仿真时间。
- Gazebo/TurtleBot4 bridge -> `/scan`、`/odom`、`/oakd/rgb/preview/*`：传感器和里程计。
- localization -> `map -> odom` TF。
- ros2_control -> `/controller_manager/list_controllers` 和 diffdrive controller。
- Nav2 -> `/navigate_to_pose` action、路径规划、行为树执行。
- mission -> `/align_to_apriltag`、`/wait_for_tag_removed`、`/door_traverse` 三个自定义 action。

控制器状态检查：

```bash
ros2 service call /controller_manager/list_controllers controller_manager_msgs/srv/ListControllers {}
```

验收标准：你能回答机器人为什么会动：Nav2 或行为 server 发 `/cmd_vel`，diffdrive controller 结合 ros2_control/Gazebo 执行，`/odom` 和 TF 再反馈给 Nav2/RViz。

---

## 4. L2：手动驾驶

目标：不依赖 Nav2，直接验证运动链路。

注意：本工程 Nav2 参数使用 stamped velocity，手动调试也发 `geometry_msgs/msg/TwistStamped`，不要发旧式 `geometry_msgs/msg/Twist`。

低速前进：

```bash
ros2 topic pub --rate 5 /cmd_vel geometry_msgs/msg/TwistStamped \
  '{header: {frame_id: base_link}, twist: {linear: {x: 0.06}, angular: {z: 0.0}}}'
```

原地慢速旋转：

```bash
ros2 topic pub --rate 5 /cmd_vel geometry_msgs/msg/TwistStamped \
  '{header: {frame_id: base_link}, twist: {linear: {x: 0.0}, angular: {z: 0.25}}}'
```

停止：

```bash
ros2 topic pub --once /cmd_vel geometry_msgs/msg/TwistStamped \
  '{header: {frame_id: base_link}, twist: {linear: {x: 0.0}, angular: {z: 0.0}}}'
```

观察：

```bash
ros2 topic echo /odom
ros2 topic hz /odom
```

玩法扩展：

- 做一个键盘遥控脚本，封装前进、后退、左转、右转、急停。
- 做一个安全限速器，订阅目标速度，输出限幅后的 `/cmd_vel`。
- 做一个运动录制器，把 `/cmd_vel` 和 `/odom` 存成 CSV，对比实际位移和目标速度。

验收标准：机器人能在 Gazebo 中运动，RViz 里的 base_link/odom 变化一致，停止命令能可靠停住。

---

## 5. L3：Nav2 点到点导航

目标：验证地图定位、路径规划、控制器和恢复行为。

最简单玩法是在 RViz 中操作：

1. 用 `2D Pose Estimate` 确认初始位姿。
2. 用 `Nav2 Goal` 点一个可达目标。
3. 观察 global plan、local plan、costmap、机器人轨迹。

CLI 发送目标示例：

```bash
ros2 action send_goal /navigate_to_pose nav2_msgs/action/NavigateToPose \
  '{pose: {header: {frame_id: map}, pose: {position: {x: 1.0, y: 0.0, z: 0.0}, orientation: {z: 0.0, w: 1.0}}}}' \
  --feedback
```

观察 Nav2：

```bash
ros2 action list | grep navigate
ros2 topic list | grep -E 'plan|costmap|cmd_vel|goal'
ros2 topic echo --once /cmd_vel
```

玩法扩展：

- 在 RViz 里连续发送不同目标点，观察路径是否贴墙、是否绕障碍。
- 故意点到不可达区域，观察 Nav2 的失败和恢复行为。
- 调整 `src/tourbot_bringup/config/nav2_params.yaml`，比较机器人跟踪路径的稳定性。
- 将同一批目标点写成脚本，形成导航回归测试。

验收标准：机器人能在 warehouse 地图上完成点到点移动；目标不可达时不是静默失败，而是能从 action feedback/result 和日志判断原因。

---

## 6. L4：传感器可视化

目标：把仿真机器人的眼睛和雷达看清楚。

检查传感器频率：

```bash
ros2 topic hz /scan
ros2 topic hz /oakd/rgb/preview/image_raw
ros2 topic hz /oakd/rgb/preview/camera_info
ros2 topic hz /oakd/rgb/preview/depth
ros2 topic hz /oakd/rgb/preview/depth/points
```

查看单帧信息：

```bash
ros2 topic echo --once /oakd/rgb/preview/camera_info
ros2 topic echo --once /scan
```

RViz 玩法：

- 添加 `LaserScan`，topic 选 `/scan`。
- 添加 `Image` 或 `Camera`，topic 选 `/oakd/rgb/preview/image_raw`。
- 添加 `PointCloud2`，topic 选 `/oakd/rgb/preview/depth/points`。
- 固定坐标系用 `map` 或 `odom`，看 TF 是否稳定。

玩法扩展：

- 做传感器健康面板：频率、延迟、最近一帧时间戳、是否断流。
- 做低频/丢帧报警：例如 `/scan` 低于阈值就打日志。
- 录制 RGB+depth+odom bag，用于离线 AprilTag 或视觉算法调参。

验收标准：RGB、深度、点云、scan 在 RViz 中都能可视化，且时间戳随 `/clock` 正常推进。

---

## 7. L5：AprilTag 感知玩法

目标：理解 AprilTag pipeline，以及它如何服务 landmark 确认和行为控制。

单独启动 AprilTag pipeline：

```bash
$DC run --rm --no-deps dev bash -lc '
  cd /ws && source install/setup.bash
  ros2 launch tourbot_perception apriltag_pipeline.launch.py
'
```

另开终端观察：

```bash
$DC exec sim bash
cd /ws
source install/setup.bash
ros2 topic echo /detections
ros2 topic echo --once /tf
```

当前配置文件：

```text
src/tourbot_perception/config/apriltags_36h11.yaml
```

当前关键配置：

```yaml
family: 36h11
size: 0.162
max_hamming: 0
z_up: true
```

重要现实限制：默认 warehouse world 不包含与 `landmarks.yaml` 对应的 AprilTag 模型；自定义 `cardboard_city/world.sdf` 当前也还只是基础世界，没有墙体、门或 tag 模型。因此：

- 没有可见 tag 时，`/detections` 为空是正常现象。
- `wait_for_tag_removed` 可以在 tag 不可见时成功，但这只验证 action 逻辑，不代表真实门流程完成。
- `align_to_apriltag` 需要目标 tag 出现在相机画面中，否则会搜索到超时。

玩法扩展：

- 在自定义 world 中放置 36h11 tag 平面模型，让 OAK-D 相机能看到。
- 做一个 tag 质量面板：显示 id、decision_margin、中心点误差、最近出现时间。
- 对比 tag size 配置错误时的 pose 偏差。
- 用不同光照、距离、角度测试 AprilTag 检出鲁棒性。

验收标准：当相机画面里确实有 36h11 tag 时，`/detections` 出现对应 `id`，并且 `/tf` 中出现 tag frame。

---

## 8. L6：单行为 Action 玩法

目标：不跑完整 mission，直接验证每个行为 server。

### 8.1 启动行为 server

最稳的方式是单独运行需要的 server，避免 `mission.launch.py` 自动启动 `tour_deliberation_node` 后开始跑完整任务。

终端 A：

```bash
$DC run --rm --no-deps dev bash -lc '
  cd /ws && source install/setup.bash
  ros2 run tourbot_behaviors align_to_apriltag_server
'
```

终端 B：

```bash
$DC run --rm --no-deps dev bash -lc '
  cd /ws && source install/setup.bash
  ros2 run tourbot_behaviors wait_for_tag_removed_server
'
```

终端 C：

```bash
$DC run --rm --no-deps dev bash -lc '
  cd /ws && source install/setup.bash
  ros2 run tourbot_behaviors door_behavior_server
'
```

### 8.2 对齐 AprilTag

前提：目标 tag 必须可见。

```bash
ros2 action send_goal /align_to_apriltag tourbot_interfaces/action/AlignToAprilTag \
  '{tag_id: 3, timeout_sec: 20.0, x_tolerance_px: 8.0}' \
  --feedback
```

看点：

- tag 不可见时 feedback state 应为 `searching_for_tag`。
- tag 可见但未居中时 state 应为 `aligning`。
- 水平误差小于容差后 result 应成功。

### 8.3 等待门 tag 消失

```bash
ros2 action send_goal /wait_for_tag_removed tourbot_interfaces/action/WaitForTagRemoved \
  '{tag_id: 1, timeout_sec: 30.0, missing_duration_sec: 3.0}' \
  --feedback
```

看点：

- tag 可见时 state 为 `TAG_VISIBLE`。
- tag 消失后 state 为 `TAG_MISSING`，累计 missing time。
- 缺失时间达到 `missing_duration_sec` 后成功。

### 8.4 门穿越

只支持 `tag_id=1` 和 `tag_id=2`：

- `tag_id=1`：outward door，不后退，等待后向前穿越。
- `tag_id=2`：inward door，转身、后退、转回、等待、向前穿越。

示例：

```bash
ros2 action send_goal /door_traverse tourbot_interfaces/action/DoorTraverse \
  '{tag_id: 1, backup_distance: 0.0, backup_speed: 0.0, wait_seconds: 2.0, forward_distance: 0.8, forward_speed: 0.12}' \
  --feedback
```

```bash
ros2 action send_goal /door_traverse tourbot_interfaces/action/DoorTraverse \
  '{tag_id: 2, backup_distance: 0.4, backup_speed: 0.12, wait_seconds: 2.0, forward_distance: 0.8, forward_speed: 0.12}' \
  --feedback
```

注意：`DoorTraverse` 会直接发布 `/cmd_vel`，会让仿真机器人移动；不要在真实机器人同 domain 下误发。

玩法扩展：

- 给 action server 增加更详细 feedback，例如阶段耗时、目标距离、剩余距离。
- 给每个 action 加 pytest/launch test，用 mock detections/odom 做自动回归。
- 将门行为从固定流程改成基于传感器判断的闭环策略。

验收标准：每个 action 的 accepted、feedback、result 都可解释，失败时能看出是 tag 不可见、odom 缺失、超时还是 goal 参数非法。

---

## 9. L7：完整 Tour Mission

目标：跑通导航到 landmark -> 对齐 tag -> 门等待/门穿越或转身离开 -> 下一个 landmark 的完整任务链。

推荐启动方式：

```bash
$DC --profile robot stop robot
$DC --profile sim up -d sim
$DC --profile mission up mission
```

`mission.launch.py` 会启动：

- `tourbot_perception/launch/apriltag_pipeline.launch.py`
- `align_to_apriltag_server`
- `wait_for_tag_removed_server`
- `door_behavior_server`
- `tour_deliberation_node`

当前 mission 逻辑：

- 固定加载 `tourbot_landmarks/config/cardboard_city/landmarks.yaml`。
- 以 `home` 作为初始位姿。
- 用最近邻贪心算法生成访问顺序。
- 对每个 landmark 调用 Nav2 到点。
- 到点后调用 `/align_to_apriltag`。
- `tag_id=1` 或 `tag_id=2` 时额外执行门流程。
- 非门 tag 完成后旋转 180 度离开。
- 最后回到 `home`。

现实限制：当前默认 warehouse 和自定义 `world.sdf` 都没有布置匹配的 AprilTag/门/墙体资产，所以完整 mission 很可能在对齐 tag 阶段超时。这个不是 action server 或 Nav2 本身坏了，而是场景资产还没补齐。

玩法扩展：

- 先把 mission 当任务编排器看，用日志确认它按预期发 goal。
- 用手动 topic/action 注入替代真实 tag，做 mission 逻辑干跑。
- 补齐 world 中的 tag 后，再追求全自动 tour。
- 给 mission 增加失败策略：重试、跳过、回家、人工介入。

验收标准：mission 日志能清楚显示当前 landmark、Nav2 goal、action goal、成功/失败原因；如果失败，能明确是场景缺 tag、导航失败还是行为动作失败。

---

## 10. L8：改 Landmarks 和讲解点

目标：把工程从固定 demo 变成可配置 tour。

主配置文件：

```text
src/tourbot_landmarks/config/cardboard_city/landmarks.yaml
```

当前结构：

```yaml
home:
  tag_id: 0
  x: 0
  y: 0
  theta: NORTH

landmarks:
  - name: door_outward
    tag_id: 1
    x: 3.14
    y: 0
    theta: SOUTH
```

方向值来自 TurtleBot4 directions，当前代码会用：

```text
NORTH, SOUTH, EAST, WEST, NORTH_EAST, NORTH_WEST, SOUTH_EAST, SOUTH_WEST
```

修改后重建相关包：

```bash
$DC run --rm build
```

或在容器内局部构建：

```bash
colcon build --symlink-install --packages-select tourbot_landmarks tourbot_mission
source install/setup.bash
```

玩法扩展：

- 做一条 3 点短 tour，专门用于快速 smoke test。
- 把 `landmarks.yaml` 扩展出 `description`、`audio_file`、`category`、`stay_seconds` 字段。
- 给不同场馆建立不同目录，例如 `museum_a`、`warehouse_lab`、`office_demo`。
- 把 `tour_deliberation_node.py` 中固定的 `map_name = 'cardboard_city'` 改成 ROS 参数，让同一个镜像支持多张地图。

验收标准：修改 YAML 后 mission 访问顺序和目标位置确实变化；日志能打印出新的 landmark name/tag_id。

---

## 11. L9：改 World、Map 和 AprilTag 资产

目标：让完整 tour 不再依赖手动注入，而是在 Gazebo 里自然发生。

关键文件：

```text
src/tourbot_bringup/worlds/cardboard_city/world.sdf
src/tourbot_bringup/maps/cardboard_city/map_area.yaml
src/tourbot_bringup/maps/cardboard_city/map_area.pgm
src/tourbot_landmarks/config/cardboard_city/landmarks.yaml
```

注意：`sim.launch.py` 的默认 `custom_world` 写成了 `cardboard_city.sdf`，但仓库实际文件是 `world.sdf`。并且 TurtleBot4 下游 launch 会自动追加 `.sdf`，所以传绝对路径时不要带 `.sdf` 后缀。

自定义 world 启动示例：

```bash
$DC run --rm --no-deps dev bash -lc '
  cd /ws && source install/setup.bash
  vglrun -d :0 ros2 launch tourbot_bringup sim.launch.py \
    use_custom_sim:=true \
    custom_world:=/ws/install/tourbot_bringup/share/tourbot_bringup/worlds/cardboard_city/world \
    custom_map:=/ws/install/tourbot_bringup/share/tourbot_bringup/maps/cardboard_city/map_area.yaml
'
```

场景资产玩法：

- 在 `world.sdf` 中加入墙体、展台、障碍物，形成可导航环境。
- 给每个 landmark 放置一个 36h11 AprilTag 平面模型，tag id 与 `landmarks.yaml` 一致。
- 给 `tag_id=1` 和 `tag_id=2` 设计两类门场景，分别验证 outward/inward 行为。
- 重新生成或修正 `map_area.pgm` 和 `map_area.yaml`，保证地图、世界、landmarks 在同一坐标系里。
- 为每个场景记录一份预期 tour 路线图和可见 tag 截图。

验收标准：机器人从 Gazebo camera 能看到 tag，AprilTag pipeline 发布 detection；Nav2 地图目标点和实际 world 中障碍物位置一致；mission 能至少自动完成一个非门 landmark 和一个门 landmark。

---

## 12. L10：行为调参和控制策略升级

目标：让行为从能动变成稳、可调、可解释。

当前行为入口：

```text
src/tourbot_behaviors/tourbot_behaviors/align_to_apriltag_server.py
src/tourbot_behaviors/tourbot_behaviors/wait_for_tag_removed_server.py
src/tourbot_behaviors/tourbot_behaviors/door_behavior_server.py
```

当前门行为默认值在代码里声明，也有一份 YAML：

```text
src/tourbot_behaviors/config/door_behavior.yaml
```

注意：`mission.launch.py` 直接启动 `door_behavior_server`，没有把 `door_behavior.yaml` 传进去；`tourbot_behaviors/launch/door_behavior.launch.py` 会传 YAML，但同时引用了当前不存在的 `manual_door_override_node`。因此要做正式调参，建议先做一个小改造：

- 在 `mission.launch.py` 里给 `door_behavior_server` 传 `door_behavior.yaml`。
- 或修复 `door_behavior.launch.py`，移除/补齐 `manual_door_override_node`。
- 将 `align_to_apriltag_server.py` 里的 `SEARCH_ANGULAR_SPEED`、`ALIGN_KP`、`MAX_ANGULAR_SPEED` 改成 ROS 参数。

可调项目：

- AprilTag 搜索角速度。
- 对齐比例增益和最大角速度。
- 对齐像素容差。
- 门等待时间。
- inward door 后退距离、后退速度。
- forward distance 的语义和终点安全距离。
- action 超时、重试次数、失败后的恢复策略。

玩法扩展：

- 将对齐控制从 P controller 升级到带最小速度/死区/低通滤波的控制器。
- 将门穿越从 odom 开环距离升级到基于 LiDAR/视觉的闭环穿越。
- 增加 `/behavior_status` topic，给 RViz 或面板显示当前行为阶段。
- 把每次 action 的参数、耗时、结果写入 CSV，形成行为指标库。

验收标准：同一个场景重复 10 次，action 成功率、耗时、最大角速度、最终姿态误差都有记录，调参前后能量化对比。

---


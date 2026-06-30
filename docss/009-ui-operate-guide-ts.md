# RViz2 / Gazebo / HMI 操作排障与修复记录

> 日期：2026-06-30  
> 目标主机：`xiao-5080` / `5080-MS-eSport-Z890M` / Ubuntu 24.04  
> 目标仓库：`/home/xiaozy/4sim/gh-ref/tour-guide-robot/Hyaxon-tour-guide-robot`  
> 参考截图：`/tmp/ss/ss2026-06-30-4.33.58.png`  
> 注意：本文所有命令都在 `xiao-5080` 上执行，不在当前 Dell notebook 的仓库里执行。

---

## 1. 当前结论

截图中的 Gazebo、RViz2 和 TurtleBot4 HMI 已经起来，但不能直接点 `Nav2 Goal` 的根因不是 UI，而是导航链路当时没有闭合：

- `odom -> base_link` TF 原先只以不兼容 Nav2 监听器的 QoS 发布，Nav2/AMCL 查不到。
- `amcl` 在没有初始位姿前不会发布 `map -> odom`。
- Nav2 自启动时如果早于定位完成，会把部分 lifecycle 节点留在 `inactive`。

本次已在远端仓库修复：

- `src/tourbot_bringup/launch/sim.launch.py`
  - 将 TurtleBot4 仿真、localization、Nav2、RViz 拆成两阶段启动。
  - Gazebo/控制器先启动，30 秒后再启动 localization、Nav2 和 RViz。
  - 修正 custom world 默认路径为 `world`，避免上游再拼 `.sdf` 后找错文件。
  - 启动两个兼容节点：`odom_tf_compat`、`nav2_post_localization_activator`。
- `src/tourbot_bringup/tourbot_bringup/odom_tf_compat.py`
  - 订阅 `/odom`，用标准 `VOLATILE` TF QoS 发布 `odom -> base_link`。
- `src/tourbot_bringup/tourbot_bringup/nav2_post_localization_activator.py`
  - 等 AMCL 发布 `map -> base_link` 后，自动激活仍处于 `inactive` 的 Nav2 lifecycle 节点。
- `src/tourbot_bringup/setup.py`、`src/tourbot_bringup/package.xml`
  - 注册两个 console scripts 并补齐运行依赖。

已验证：

- `colcon build --symlink-install --packages-select tourbot_bringup` 成功。
- `sim` 容器重启成功。
- `odom -> base_link` 可被标准 `tf2_echo` 查到。
- 发布初始位姿后，`/amcl_pose` 有输出，`map -> base_link` 可查。
- 自动激活日志显示 Nav2 节点已补激活：`planner_server`、`route_server`、`behavior_server`、`velocity_smoother`、`collision_monitor`、`bt_navigator`、`waypoint_follower`、`docking_server`。

---

## 2. 启动与进入容器

从 Dell notebook SSH 到远端：

```bash
ssh xiao-5080
cd /home/xiaozy/4sim/gh-ref/tour-guide-robot/Hyaxon-tour-guide-robot
export DC='docker compose -f docker_stuff/compose.yaml'
```

只跑仿真，先停掉可能冲突的 robot / mission：

```bash
$DC --profile robot --profile mission stop robot mission
$DC --profile sim up -d --force-recreate sim
```

进入容器：

```bash
$DC exec sim bash
cd /ws
source install/setup.bash
```

启动后先等 30-60 秒。Gazebo、机器人 spawn、ros2_control、bridge、Nav2、RViz 都需要时间建立图。

---

## 3. 定位前检查

检查关键 topic/action：

```bash
ros2 topic list | egrep '^/(clock|map|odom|scan|tf|tf_static|initialpose|goal_pose|cmd_vel)$'
ros2 action list | egrep '^/(navigate_to_pose|navigate_through_poses|follow_path)$'
```

检查两个修复节点：

```bash
ros2 node list | egrep 'odom_tf_compat|nav2_post_localization_activator'
```

应看到：

```text
/odom_tf_compat
/nav2_post_localization_activator
```

检查里程计 TF：

```bash
timeout 8 ros2 run tf2_ros tf2_echo odom base_link
```

能看到 translation / rotation 就说明机器人本体 TF 已闭合。若这里失败，不要做定位，也不要发目标。

---

## 4. 在 RViz2 里定位

定位入口是 RViz2 顶部工具栏，不是 Gazebo 右侧 HMI。

操作步骤：

1. 确认 RViz2 左上 `Fixed Frame` 是 `map`。
2. 等地图显示稳定，LaserScan / RobotModel 不再持续大面积红色报错。
3. 点击顶部工具栏 `2D Pose Estimate`。
4. 在地图上机器人实际所在位置按下鼠标左键。
5. 按住拖动出机器人朝向，然后松开。
6. 等 2-10 秒，让 AMCL 收敛并发布 `map -> odom`。

命令行确认：

```bash
timeout 8 ros2 topic echo --once /amcl_pose
timeout 8 ros2 run tf2_ros tf2_echo map base_link
```

成功后应能看到 `/amcl_pose`，并且 `map -> base_link` 可查。

本次修复后，`nav2_post_localization_activator` 会在 `map -> base_link` 出现后自动激活 Nav2。确认方式：

```bash
for n in map_server amcl controller_server planner_server route_server behavior_server bt_navigator waypoint_follower; do
  printf '%-22s ' "$n"
  timeout 4 ros2 lifecycle get "/$n" || echo 'no response'
done
```

期望主要节点为：

```text
active [3]
```

---

## 5. 发送导航目标

只有在完成第 4 节定位后，才发送目标。

RViz2 操作：

1. 点击顶部工具栏 `Nav2 Goal`。
2. 在地图空旷可通行区域按下鼠标左键。
3. 拖动箭头设置最终朝向。
4. 松开鼠标后等待全局路径出现。
5. 观察 Navigation 2 面板的 feedback、remaining distance、ETA。

目标点选择原则：

- 点在地图白色或浅色可通行区域。
- 不要点墙体、障碍物、未知区域或机器人半径贴边位置。
- 初次测试选 0.5-1.5 米内的小目标。
- 机器人开始移动后，不要同时用 Gazebo Teleop 或 HMI Wall Follow。

命令行只做状态确认，不建议第一次直接 CLI 发目标：

```bash
ros2 action info /navigate_to_pose
```

如果 RViz2 里想取消导航，用 Navigation 2 面板的 cancel 按钮。紧急情况下可在 Gazebo HMI 用 `EStop`，或暂停 Gazebo 仿真。

---

## 6. Gazebo 右侧 HMI 怎么用

右侧 `Turtlebot4 HMI` 不是地图导航目标入口，它主要控制 TurtleBot4 仿真功能：

- `Dock` / `Undock`：对接与脱离充电桩流程。
- `EStop`：急停。
- `Wall Follow Left/Right`：沿墙行为。
- `Power` / `Help`：TurtleBot4 HMI 菜单功能。
- Teleop：速度控制，发布到 `/cmd_vel`。

使用原则：

- 做 Nav2 点到点导航时，不要同时开 Teleop 或 Wall Follow。
- 机器人不动时，先看 RViz2 的定位和 Nav2 lifecycle，不要先怀疑 HMI。
- HMI 可用于急停或 dock/undock，不用于设置 `/initialpose` 和 `/navigate_to_pose`。

---

## 7. 常见故障与处理

### 7.1 RViz 能看到地图，但不能发目标

先查：

```bash
timeout 8 ros2 run tf2_ros tf2_echo map base_link
ros2 lifecycle get /bt_navigator
ros2 lifecycle get /planner_server
```

若 `map -> base_link` 不存在，回到 RViz2 重新做 `2D Pose Estimate`。

若定位后仍有 lifecycle 节点 inactive，查看自动激活日志：

```bash
docker logs --tail 220 hyaxon-tour-guide-robot-sim-1 2>&1 | grep nav2_post_localization
```

临时手动补激活：

```bash
for n in /planner_server /route_server /behavior_server /velocity_smoother /collision_monitor /bt_navigator /waypoint_follower /docking_server; do
  timeout 15 ros2 lifecycle set "$n" activate || true
done
```

### 7.2 AMCL 提示 Please set the initial pose

这是正常提示，表示还没在 RViz2 里定位。执行 `2D Pose Estimate`。

### 7.3 odom -> base_link 不存在

检查修复节点和 `/odom`：

```bash
ros2 topic echo --once /odom
ros2 node list | grep odom_tf_compat
ros2 topic info /tf -v | grep -A8 odom_tf_compat
```

如果 `odom_tf_compat` 不在，重建并重启：

```bash
exit
cd /home/xiaozy/4sim/gh-ref/tour-guide-robot/Hyaxon-tour-guide-robot
$DC run --rm --no-deps dev bash -lc "source /opt/ros/jazzy/setup.bash && colcon build --symlink-install --packages-select tourbot_bringup"
$DC --profile sim up -d --force-recreate sim
```

### 7.4 点击 Nav2 Goal 后机器人不动

按顺序查：

```bash
ros2 action info /navigate_to_pose
ros2 lifecycle get /bt_navigator
ros2 topic echo --once /cmd_vel_nav
ros2 topic echo --once /cmd_vel
ros2 topic echo --once /diffdrive_controller/cmd_vel
```

正常速度链路是：

```text
controller_server
  -> /cmd_vel_nav
  -> velocity_smoother
  -> /cmd_vel_smoothed
  -> collision_monitor
  -> /cmd_vel
  -> motion_control
  -> /diffdrive_controller/cmd_vel
  -> cmd_vel_bridge
  -> Gazebo /model/turtlebot4/cmd_vel
  -> diffdrive_controller
```

若 `/cmd_vel_nav` 有速度但 `/cmd_vel_smoothed` 没有，查 `velocity_smoother`。  
若 `/cmd_vel_smoothed` 有速度但 `/cmd_vel` 没有，查 `collision_monitor`。  
若 `/cmd_vel` 有速度但 `/diffdrive_controller/cmd_vel` 没有，查 `motion_control`。  
若 `/diffdrive_controller/cmd_vel` 有速度但 Gazebo 不动，查 Gazebo 是否暂停、diffdrive controller 是否拒收命令。

查看 Gazebo diffdrive 是否拒收旧命令：

```bash
docker logs --tail 300 hyaxon-tour-guide-robot-sim-1 2>&1 | grep 'diffdrive_controller'
```

如果出现：

```text
Ignoring the received message ... because it is older than the current time ... exceeds the allowed timeout (0.5000)
```

含义是速度命令已经到 Gazebo，但 `TwistStamped.header.stamp` 太旧，Gazebo 差速控制器按安全策略拒收。这通常发生在：

- goal 刚开始或 recovery 刚结束时，链路上还残留上一条 0 速度命令；
- controller 触发 `Failed to make progress`，BT 做清 costmap / recovery，速度链短暂停顿；
- 系统负载较高，Nav2 控制循环或 bridge 有延迟。

判断命令时间戳是否新鲜：

```bash
echo CLOCK
timeout 5 ros2 topic echo --qos-reliability best_effort --once /clock
echo CMD_NAV
timeout 5 ros2 topic echo --once /cmd_vel_nav
echo CMD_SMOOTH
timeout 5 ros2 topic echo --once /cmd_vel_smoothed
echo CMD
timeout 5 ros2 topic echo --once /cmd_vel
echo DIFFDRIVE
timeout 5 ros2 topic echo --once /diffdrive_controller/cmd_vel
```

用 `/clock` 的时间减去每条 `header.stamp`。如果差值持续大于 `0.5s`，Gazebo 会拒收；如果差值在 `0.05-0.1s` 左右，时间戳正常。

不要只看 `/odom` 判断 Gazebo 里是否真的移动。`/odom` 是差速控制器里程计，排查 Gazebo 真实位置时看 ground truth：

```bash
timeout 5 ros2 topic echo --once /_internal/sim_ground_truth_pose | grep -A12 -B3 'child_frame_id: turtlebot4'
```

重点看这一段：

```text
frame_id: warehouse
child_frame_id: turtlebot4
translation:
  x: ...
  y: ...
```

这里才是 Gazebo 世界坐标下机器人实体的位置。

### 7.5 RViz2 出现多个 rviz2 重名警告

当前容器里可能出现多个 `/rviz2` 节点名，通常来自 RViz 主进程和 dialog/action client。只要 Navigation 2 面板、`/initialpose`、`/navigate_to_pose` 可用，可先忽略。若操作混乱，重启 `sim` 容器。

---

## 8. 本次验收命令摘要

在远端执行：

```bash
cd /home/xiaozy/4sim/gh-ref/tour-guide-robot/Hyaxon-tour-guide-robot
export DC='docker compose -f docker_stuff/compose.yaml'

$DC run --rm --no-deps dev bash -lc "source /opt/ros/jazzy/setup.bash && colcon build --symlink-install --packages-select tourbot_bringup"
$DC --profile sim up -d --force-recreate sim
```

容器内验证：

```bash
cd /ws
source install/setup.bash
timeout 8 ros2 run tf2_ros tf2_echo odom base_link
timeout 8 ros2 topic echo --once /amcl_pose
timeout 8 ros2 run tf2_ros tf2_echo map base_link
ros2 action info /navigate_to_pose
```

初次修复时只验证到定位链路和 Nav2 action server 可用；后续现场排查已经观察到实际 `Nav2 Goal` 执行和 Gazebo ground truth 位姿变化，见第 9 节。

---

## 9. 2026-06-30 目标后 Gazebo 看似不动的现场排查

用户在 RViz2 指定目标后，Gazebo 画面里机器人看起来没有同步移动。现场排查结果如下。

Nav2 确实收到目标：

```text
bt_navigator: Begin navigating from current location (0.04, -0.11) to (0.76, -0.06)
controller_server: Received a goal, begin computing control effort.
```

之后又收到一个更远目标：

```text
bt_navigator: Begin navigating from current location (0.45, -0.12) to (2.66, -2.88)
```

Nav2 期间多次触发：

```text
controller_server: Failed to make progress
controller_server: [follow_path] [ActionServer] Aborting handle.
local_costmap: Received request to clear entirely the local_costmap
```

这表示控制器认为机器人一段时间内没有满足进度检查，于是执行 recovery，再重新跟踪路径。当前参数为：

```text
progress_checker.required_movement_radius = 0.5
progress_checker.movement_time_allowance = 10.0
FollowPath.vx_max = 0.5
FollowPath.vx_min = -0.35
FollowPath.wz_max = 1.9
```

Gazebo 同时出现差速控制器拒收旧速度命令：

```text
diffdrive_controller: Ignoring the received message (timestamp 623.0490000000)
because it is older than the current time by 0.5010000000 seconds,
which exceeds the allowed timeout (0.5000)
```

这说明速度命令已经进入 Gazebo，但部分命令时间戳超过 0.5 秒，被 Gazebo 拒收。拒收的通常是 recovery / 停车阶段遗留的 0 速度命令；当 controller 持续输出新速度后，延迟恢复到正常范围。

现场测得速度链路延迟：

```text
/cmd_vel_nav:                 lag=+0.000s vx=+0.345 wz=-0.273
/cmd_vel_smoothed:            lag=+0.027s vx=+0.260 wz=-0.273
/cmd_vel:                     lag=+0.045s vx=+0.260 wz=-0.279
/diffdrive_controller/cmd_vel: lag=+0.075s vx=+0.260 wz=-0.279
```

这表示目标执行中的新速度命令是新鲜的，可以被 Gazebo 接收。

Gazebo ground truth 也确认机器人实体最后确实移动到了目标附近：

```text
frame_id: warehouse
child_frame_id: turtlebot4
translation:
  x: 2.68886070437523
  y: -2.698822211574801
```

而目标日志为：

```text
to (2.66, -2.88)
```

所以这次不是“目标没有发送”或“Gazebo 完全不动”。更准确的原因是：

- Nav2 目标已送达，action server 正常工作；
- 早期和 recovery 阶段存在旧时间戳速度命令，Gazebo diffdrive 会拒收；
- 控制器多次 `Failed to make progress`，导致视觉上出现停顿、恢复、再走；
- Gazebo 真实位姿和 `/odom`、RViz map 位姿不是同一个坐标源，排查时必须看 `/_internal/sim_ground_truth_pose`；
- 最终 ground truth 显示 Gazebo 实体已移动到目标附近。

如果再次出现“看起来没动”，按下面顺序判断：

```bash
# 1. 目标是否进入 Nav2
docker logs --tail 300 hyaxon-tour-guide-robot-sim-1 2>&1 | grep -E 'Begin navigating|Goal succeeded|Failed to make progress'

# 2. Nav2 是否还在发速度
timeout 5 ros2 topic echo --once /cmd_vel_nav
timeout 5 ros2 topic echo --once /cmd_vel
timeout 5 ros2 topic echo --once /diffdrive_controller/cmd_vel

# 3. Gazebo 是否拒收旧速度
docker logs --tail 300 hyaxon-tour-guide-robot-sim-1 2>&1 | grep 'Ignoring the received message'

# 4. Gazebo 实体真实位置
timeout 5 ros2 topic echo --once /_internal/sim_ground_truth_pose | grep -A12 -B3 'child_frame_id: turtlebot4'
```

若第 2 步速度为 0，但 action 仍在执行，重点查 costmap / collision monitor / progress checker。  
若第 2 步速度非 0、第 3 步持续拒收，重点查速度时间戳和系统负载。  
若第 4 步坐标在变，只是 Gazebo 视角没跟随或移动幅度小；切换 Gazebo camera 跟随机器人或放大视图再观察。

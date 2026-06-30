# RViz2 / Gazebo / TurtleBot4 HMI 现场操作指南

> 编写日期：2026-06-30  
> 目标主机：`xiao-5080` / `5080-MS-eSport-Z890M` / Ubuntu 24.04  
> 目标仓库：`/home/xiaozy/4sim/gh-ref/tour-guide-robot/Hyaxon-tour-guide-robot`  
> 参考截图：`/tmp/ss/ss2026-06-30-4.33.58.png`    ![p1](https://i.imgur.com/PurgRDu.png) ![p2](https://i.imgur.com/jDfwCjG.png)
> 操作原则：所有命令都在 `xiao-5080` 上执行，不在当前 Dell notebook 上改仓库内容。

---

## 0. 先说结论

截图里已经能看到 Gazebo、RViz2 地图和右侧 TurtleBot4 HMI，说明 GUI、Gazebo 和 ROS graph 大体起来了；但这还不是可以直接点 `Nav2 Goal` 导航的状态。

从截图和远端排查看，当前关键异常是：

- RViz2 左下角 Navigation 2 面板显示 `Navigation: inactive`、`Localization: inactive`。
- RViz2 左侧 `Global Status: Error`，`RobotModel` 为红色。
- 运行中 `map -> base_link` TF 不存在。
- `amcl`、`bt_navigator`、`behavior_server`、`waypoint_follower`、`velocity_smoother` 等 lifecycle 节点曾处于 inactive。
- `sim` 日志持续出现 `StaticLayer: "map" passed to lookupTransform argument target_frame does not exist`。

所以当前下一步不是先发目标，而是：

1. 确认 `sim` 是唯一运行的导航栈。
2. 让 localization / Nav2 lifecycle 进入 active。
3. 用 RViz2 的 `2D Pose Estimate` 设置初始位姿。
4. 确认 `map -> odom -> base_link` TF 链路成立。
5. 再用 RViz2 的 `Nav2 Goal` 或 CLI action 发送导航目标。

右侧 Gazebo HMI 不是发送地图目标的入口。HMI 主要用于 TurtleBot4 的 `Dock`、`Undock`、`EStop`、`Wall Follow`、Teleop 等仿真控制；地图定位和点到点导航应优先在 RViz2 里完成。

---

## 1. 远端入口

从 Dell notebook 只做 SSH 入口：

```bash
ssh xiao-5080
cd /home/xiaozy/4sim/gh-ref/tour-guide-robot/Hyaxon-tour-guide-robot
export DC='docker compose -f docker_stuff/compose.yaml'
```

确认确实在 5080 主机：

```bash
hostname
pwd
```

期望：

```text
5080-MS-eSport-Z890M
/home/xiaozy/4sim/gh-ref/tour-guide-robot/Hyaxon-tour-guide-robot
```

---

## 2. 这个界面各部分代表什么

### 2.1 RViz2 窗口

截图中 RViz2 标题为：

```text
/opt/ros/jazzy/share/turtlebot4_viz/rviz/navigation.rviz
```

这个 RViz 配置的关键点是：

- `Fixed Frame: map`
- `2D Pose Estimate` 发布到 `/initialpose`
- `Nav2 Goal` 用于向 Nav2 发送导航目标
- Navigation 2 面板显示 localization / navigation 状态、feedback、ETA、剩余距离

正常可导航时应该看到：

- `Localization: active`
- `Navigation: active`
- `map -> odom -> base_link` TF 存在
- 机器人模型、LaserScan、costmap 和 plan 不再大面积报错

### 2.2 Gazebo 窗口

Gazebo 负责仿真世界、机器人实体、传感器和右侧 HMI / Teleop 插件。

截图右侧的 `Turtlebot4 HMI` 来自 TurtleBot4 Gazebo GUI 插件。其配置在容器内：

```text
/opt/ros/jazzy/share/turtlebot4_gz_bringup/config/turtlebot4_node.yaml
/opt/ros/jazzy/share/turtlebot4_gz_bringup/gui/standard/gui.config
```

HMI 菜单支持：

```text
Dock
Undock
EStop
Wall Follow Left
Wall Follow Right
Power
Help
```

Teleop 插件发布到：

```text
/cmd_vel
```

第一次做 RViz 导航时，HMI 只建议用于观察和紧急停止；不要同时用 Teleop、Wall Follow 和 Nav2，否则多个控制源会同时抢 `/cmd_vel`。

### 2.3 本工程源码入口

和当前操作直接相关的文件：

```text
docker_stuff/compose.yaml
src/tourbot_bringup/launch/sim.launch.py
src/tourbot_bringup/launch/robot.launch.py
src/tourbot_bringup/launch/mission.launch.py
src/tourbot_bringup/config/nav2_params.yaml
src/tourbot_landmarks/config/cardboard_city/landmarks.yaml
src/tourbot_mission/tourbot_mission/tour_deliberation_node.py
src/tourbot_behaviors/tourbot_behaviors/align_to_apriltag_server.py
src/tourbot_behaviors/tourbot_behaviors/door_behavior_server.py
```

`sim.launch.py` 默认已经通过 TurtleBot4 bringup 启动：

- Gazebo
- TurtleBot4 spawn
- ROS-Gazebo bridge
- localization
- Nav2
- RViz2

所以手动定位和点到点导航时，只需要 `sim` profile，不要再同时启动 `robot` profile。

`mission.launch.py` 会启动 AprilTag perception、行为 action server 和 `tour_deliberation_node`。它是完整任务入口，不是第一次手动点目标的入口。

---

## 3. 导航前置检查

先确认只有 `sim` 在跑，避免同一个 `ROS_DOMAIN_ID=42` 里出现重复 Nav2 / RViz / TF：

```bash
$DC --profile robot --profile mission stop robot mission
$DC ps
```

期望只看到 `sim` 运行。

进入 `sim` 容器：

```bash
$DC exec sim bash
cd /ws
source install/setup.bash
```

检查 topic / action：

```bash
ros2 topic list | egrep '^/(clock|map|odom|scan|tf|tf_static|initialpose|goal_pose|cmd_vel)$'
ros2 action list | egrep '^/(navigate_to_pose|navigate_through_poses|follow_path)$'
```

至少应看到：

```text
/clock
/map
/odom
/scan
/tf
/tf_static
/initialpose
/goal_pose
/cmd_vel
/navigate_to_pose
```

检查 lifecycle：

```bash
for n in map_server amcl planner_server controller_server bt_navigator behavior_server waypoint_follower velocity_smoother; do
  printf '%-24s ' "$n"
  timeout 3 ros2 lifecycle get "/$n" || echo 'no response'
done
```

可导航前的期望状态：

```text
map_server               active [3]
amcl                     active [3]
planner_server           active [3]
controller_server        active [3]
bt_navigator             active [3]
behavior_server          active [3]
waypoint_follower        active [3]
velocity_smoother        active [3]
```

检查里程计 TF：

```bash
timeout 5 ros2 run tf2_ros tf2_echo odom base_link
```

这里必须能看到 transform。如果 `odom -> base_link` 都没有，说明机器人 spawn、controller、bridge 或 TF 本身还没起来，先不要设置初始位姿，也不要发 Nav2 goal。

检查地图 TF：

```bash
timeout 5 ros2 run tf2_ros tf2_echo map base_link
```

如果还没有设置初始位姿，`map -> base_link` 可能暂时没有；设置 `2D Pose Estimate` 后它必须出现。

---

## 4. 如果像截图一样是 inactive，先恢复运行态

当前截图对应的状态是 lifecycle 没有完整 active。建议先重启 `sim`，比手工逐个 lifecycle transition 更干净。

在远端仓库根目录执行：

```bash
cd /home/xiaozy/4sim/gh-ref/tour-guide-robot/Hyaxon-tour-guide-robot
export DC='docker compose -f docker_stuff/compose.yaml'

$DC --profile robot --profile mission stop robot mission
$DC --profile sim up -d --force-recreate sim
$DC logs --tail=160 sim
```

等待 Gazebo、RViz2、map server、Nav2 都启动完，再进入容器重复第 3 节检查。

如果日志里继续出现下面两类错误，说明还不能发目标：

```text
Timed out waiting for transform from base_link to odom
StaticLayer: "map" passed to lookupTransform argument target_frame does not exist
```

处理方式：

- `base_link -> odom` 缺失：优先重启 `sim`，并确认 controller 已加载。
- `map` 缺失或 `amcl` inactive：确认 localization lifecycle active，再设置初始位姿。
- `ros2 node list` 提示多个同名 `/rviz2`：关闭多余 RViz 或重启 `sim`，避免重复 GUI 节点干扰排查。

控制器检查：

```bash
ros2 service call /controller_manager/list_controllers controller_manager_msgs/srv/ListControllers {}
```

重点看 `diffdrive_controller`、`joint_state_broadcaster` 是否 active。

---

## 5. 第一步：用 RViz2 定位

定位的目标是让 AMCL 知道机器人在 `map` 坐标系里的初始位置，并发布：

```text
map -> odom -> base_link
```

### 5.1 在 RViz2 里操作

1. 在 RViz2 顶部工具栏选择 `2D Pose Estimate`。
2. 在地图上找到机器人实际所在位置。
3. 鼠标左键按住该位置，拖出一个箭头。
4. 箭头方向要指向机器人正前方。
5. 松开鼠标后观察粒子云、LaserScan 和机器人模型是否贴合地图。
6. 如果 LaserScan 和墙体不重合，重复设置 2-3 次，直到贴合。

判断定位成功：

- RViz2 左下角 `Localization` 变为 active。
- `RobotModel` 不再因为 `map` TF 大面积报错。
- `LaserScan` 与地图墙体基本重合。
- 运行下面命令能看到 `map -> base_link`：

```bash
timeout 5 ros2 run tf2_ros tf2_echo map base_link
```

截图中的 RViz2 固定视角是 top-down。定位时建议同时看 Gazebo 里的机器人朝向，避免把箭头方向拖反。

### 5.2 CLI 定位备选

如果只是做 smoke test，且确认机器人就在地图原点附近、朝向正 X，可以在容器里发布一次 `/initialpose`：

```bash
ros2 topic pub --once /initialpose geometry_msgs/msg/PoseWithCovarianceStamped \
'{header: {frame_id: map}, pose: {pose: {position: {x: 0.0, y: 0.0, z: 0.0}, orientation: {z: 0.0, w: 1.0}}}}'
```

CLI 只适合你明确知道坐标和朝向的情况。现场操作优先用 RViz2 鼠标，因为可以结合 Gazebo 画面判断机器人实际姿态。

---

## 6. 第二步：发送 Nav2 目标

确认以下条件都满足后再发目标：

```text
Localization: active
Navigation: active
map -> base_link TF 正常
/navigate_to_pose action 存在
Teleop 没有持续发布非零 /cmd_vel
HMI 没有处于 EStop
```

### 6.1 在 RViz2 里发送目标

1. 选择顶部工具栏的 `Nav2 Goal`，不要选 `Publish Point`。
2. 在地图的空白可达区域按住鼠标左键。
3. 拖出目标朝向箭头。
4. 松开鼠标，Nav2 会规划路径并开始移动。
5. 观察 RViz2 中的 global plan、local costmap、机器人轨迹和 Navigation 2 面板反馈。

正常现象：

- 地图上出现路径线。
- `/cmd_vel` 或 `/cmd_vel_smoothed` 有输出。
- Gazebo 中机器人开始移动。
- Navigation 2 面板里剩余距离、ETA、feedback 会变化。

命令行观察：

```bash
ros2 topic echo --once /goal_pose
ros2 topic echo --once /cmd_vel
ros2 topic echo --once /plan
```

如果点目标后没有动，先看：

```bash
ros2 action info /navigate_to_pose
ros2 topic hz /scan
ros2 topic hz /odom
timeout 5 ros2 run tf2_ros tf2_echo map base_link
```

### 6.2 CLI 发送目标

进入 `sim` 容器后：

```bash
ros2 action send_goal /navigate_to_pose nav2_msgs/action/NavigateToPose \
'{pose: {header: {frame_id: map}, pose: {position: {x: 1.0, y: 0.0, z: 0.0}, orientation: {z: 0.0, w: 1.0}}}}' \
--feedback
```

这个目标只用于 smoke test。实际坐标应从 RViz2 地图上的可通行区域选，不要盲目照抄。

停止机器人：

```bash
ros2 topic pub --once /cmd_vel geometry_msgs/msg/TwistStamped \
'{header: {frame_id: base_link}, twist: {linear: {x: 0.0}, angular: {z: 0.0}}}'
```

如果正在用 RViz2 goal，优先用 Navigation 2 面板的 cancel / reset 控件停止任务；上面的 `/cmd_vel` 零速度只用于兜底。

---

## 7. HMI 应该怎么用

右侧 HMI 是 TurtleBot4 仿真 HMI，不是 tour guide mission 的地图目标面板。

当前无 namespace 时，HMI 的 Namespace 输入框保持空即可。不要随便填 `robot` 或其它 namespace，否则 HMI 会去找不同命名空间下的 topic。

建议用法：

- `EStop`：紧急停机或异常运动时使用。
- `Undock`：如果机器人确实在 dock 上，需要先离 dock，再做导航。
- `Dock`：需要测试 docking 时使用，不是点到点导航的必要步骤。
- `Wall Follow Left/Right`：测试 TurtleBot4 自带沿墙行为时使用；不要和 Nav2 同时用。
- `Teleop`：手动低速试车时用；开始 Nav2 goal 前确保 Teleop 没有持续发非零速度。

不要用 HMI 做这些事：

- 不要用 HMI 设置 AMCL 初始位姿。
- 不要用 HMI 发送地图目标。
- 不要在 Nav2 正在导航时再按 Wall Follow 或持续 Teleop。

---

## 8. 手动驾驶 smoke test

如果你想先确认机器人能动，但暂时不测 Nav2，可以直接发 `/cmd_vel`。

本工程 Nav2 参数启用了 stamped velocity，所以手动命令也用 `TwistStamped`：

```bash
ros2 topic pub --rate 5 /cmd_vel geometry_msgs/msg/TwistStamped \
'{header: {frame_id: base_link}, twist: {linear: {x: 0.05}, angular: {z: 0.0}}}'
```

原地旋转：

```bash
ros2 topic pub --rate 5 /cmd_vel geometry_msgs/msg/TwistStamped \
'{header: {frame_id: base_link}, twist: {linear: {x: 0.0}, angular: {z: 0.25}}}'
```

停止：

```bash
ros2 topic pub --once /cmd_vel geometry_msgs/msg/TwistStamped \
'{header: {frame_id: base_link}, twist: {linear: {x: 0.0}, angular: {z: 0.0}}}'
```

这只验证运动链路，不代表 localization / Nav2 已经可用。

---

## 9. Tour guide mission 什么时候启动

不要在第一次 RViz 定位和点目标前启动 mission。

`src/tourbot_bringup/launch/mission.launch.py` 会启动：

- `apriltag_ros` pipeline
- `/align_to_apriltag`
- `/wait_for_tag_removed`
- `/door_traverse`
- `tour_deliberation_node`

`tour_deliberation_node.py` 会做这些事：

1. 读取 `tourbot_landmarks/config/cardboard_city/landmarks.yaml`。
2. 将 `home` 作为初始位姿。
3. 等待 Nav2 active。
4. 按最近邻顺序访问 landmarks。
5. 每个 landmark 到点后调用 `/align_to_apriltag`。
6. tag 1 / tag 2 进入门等待和门穿越逻辑。
7. 其它 tag 对齐后旋转 180 度离开。

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

重要限制：

- 当前 `sim.launch.py` 默认 `use_custom_sim:=false`，走 TurtleBot4 官方 warehouse world 和 warehouse map。
- `cardboard_city` landmarks 与默认 warehouse 不一定匹配。
- 默认 world 不保证存在与 landmarks 对应的 AprilTag / 门模型。
- 因此完整 mission 很可能在 `/align_to_apriltag` 阶段超时，这不是 RViz 点目标的问题。

只有当手动 Nav2 goal 已经稳定、AprilTag pipeline 能看到目标 tag、world/map/landmarks 对齐后，再启动 mission：

```bash
$DC --profile mission up mission
```

观察日志：

```bash
$DC logs -f mission
```

---

## 10. 常见问题定位表

| 现象 | 优先检查 | 处理 |
|---|---|---|
| RViz `Localization: inactive` | `ros2 lifecycle get /amcl` | lifecycle active 前不要发目标；必要时重启 `sim` |
| RViz `Navigation: inactive` | `ros2 lifecycle get /bt_navigator` | 确认 Nav2 lifecycle 全 active |
| `map -> base_link` 不存在 | `tf2_echo map base_link` | 先设置 `2D Pose Estimate`；若 AMCL inactive，重启 `sim` |
| `odom -> base_link` 不存在 | `tf2_echo odom base_link` | 检查 controller / bridge / Gazebo spawn，通常重启 `sim` |
| 目标点后不动 | `/cmd_vel`、action feedback、HMI EStop | 清 EStop，确认 goal 可达，确认没有 Teleop 抢速度 |
| 有 plan 但走不动 | local costmap、障碍物、collision monitor | 换空旷目标点，清 costmap，确认 LaserScan 正常 |
| 机器人乱转找 tag | `/detections` | 当前 world 可能没有对应 AprilTag，mission 会超时 |
| HMI 控制后 Nav2 异常 | `/cmd_vel` 是否持续有 Teleop | 停止 Teleop / Wall Follow，再重新发 Nav2 goal |
| 多个 `/rviz2` warning | `ros2 node list` | 关闭多余 RViz 或重启 `sim` |

清 costmap 示例：

```bash
ros2 service call /global_costmap/clear_entirely_global_costmap nav2_msgs/srv/ClearEntireCostmap {}
ros2 service call /local_costmap/clear_entirely_local_costmap nav2_msgs/srv/ClearEntireCostmap {}
```

---

## 11. 推荐的现场操作顺序

按这个顺序做最稳：

1. 只保留 `sim`，停止 `robot` 和 `mission`。
2. 如果截图仍显示 inactive，重启 `sim`。
3. 在容器里确认 `/odom`、`/scan`、`/map`、`/navigate_to_pose` 存在。
4. 确认 `odom -> base_link` TF 正常。
5. 确认 lifecycle 全部 active。
6. 在 RViz2 里用 `2D Pose Estimate` 设置初始位姿。
7. 确认 `map -> base_link` TF 正常。
8. 在 RViz2 里用 `Nav2 Goal` 点一个近距离、空旷、可达目标。
9. 观察 plan、costmap、`/cmd_vel`、Gazebo 运动。
10. 手动导航稳定后，再考虑 AprilTag 和 mission。

最小验证命令集：

```bash
cd /home/xiaozy/4sim/gh-ref/tour-guide-robot/Hyaxon-tour-guide-robot
export DC='docker compose -f docker_stuff/compose.yaml'

$DC --profile robot --profile mission stop robot mission
$DC --profile sim up -d --force-recreate sim

$DC exec sim bash
cd /ws
source install/setup.bash

ros2 action list | grep navigate_to_pose
ros2 topic list | egrep '^/(map|odom|scan|tf|initialpose|goal_pose|cmd_vel)$'
timeout 5 ros2 run tf2_ros tf2_echo odom base_link
```

然后回到 RViz2：

```text
2D Pose Estimate -> Nav2 Goal
```

不要跳过 `2D Pose Estimate`。截图当前这类 inactive 状态下，直接点 `Nav2 Goal` 大概率不会进入可解释的正常导航流程。

# 016 · Gazebo AprilTag 3D 进门穿门 SOP

> 日期：2026-07-01  
> 主机：`xiao-5080`  
> 目标：用 Gazebo 3D world + TurtleBot4 OAK-D 相机完整验证“识别门上 AprilTag -> 开门隐藏 tag -> 等待 tag 消失 -> 穿门”的闭环。

## 0. 结论

已验证通过的闭环是：

```text
Gazebo 3D world
  -> TurtleBot4 OAK-D rgbd_camera
  -> /oakd/rgb/preview/image_raw + /oakd/rgb/preview/camera_info
  -> apriltag_ros
  -> /detections
  -> align_to_apriltag
  -> /door_demo/tag_visible
  -> Gazebo set_pose 移动门板和 tag
  -> wait_for_tag_removed
  -> door_traverse
  -> /diffdrive_controller/cmd_vel + /odom
```

本 SOP 有三种入口：

- GUI 一键模式：Gazebo server 仍以 headless 方式运行，另起独立 Gazebo GUI client 观察 3D 场景。
- Headless 一键模式：无窗口，适合稳定回归。
- 两终端模式：先启动 3D world，再单独启动 door demo，适合调试。

## 1. 准备检查

进入远端主机：

```bash
ssh xiao-5080
cd ~/4sim/gh-ref/tour-guide-robot/Hyaxon-tour-guide-robot
```

确认磁盘至少有数 GB 空间：

```bash
df -h /
```

确认没有旧的同名临时 demo 容器：

```bash
docker ps --format 'table {{.ID}}\t{{.Names}}\t{{.Status}}'
```

如只需要清理本 SOP 产生的临时容器：

```bash
docker ps -a --filter 'name=tourbot-door-demo-' --format '{{.ID}}' | xargs -r docker stop
docker ps -a --filter 'name=tourbot-door-demo-' --format '{{.ID}}' | xargs -r docker rm
```

构建相关包：

```bash
docker compose -f docker_stuff/compose.yaml run --rm --no-deps dev bash -lc '
  colcon build --symlink-install --packages-select \
    tourbot_bringup tourbot_behaviors tourbot_mission tourbot_perception
'
```

## 2. GUI 一键模式

在 `xiao-5080` 桌面环境的终端运行。该模式会打开 Gazebo 3D 界面；如果通过纯 SSH 且没有 X11/VirtualGL，应优先使用第 3 节 headless 模式。

关键原则：

- 不要再用 `vglrun ros2 launch ... custom_gz_args:="-r -v 2"` 包住整条 launch。
- Gazebo server 使用 `-s --headless-rendering`，保证物理步进和传感器渲染尽量稳定。
- 只把独立 GUI client `gz sim -g` 放进 `vglrun`，避免 VirtualGL 环境影响 ROS action server、bridge 和 controller。

```bash
cd ~/4sim/gh-ref/tour-guide-robot/Hyaxon-tour-guide-robot
export ROS_DOMAIN_ID=77
export GZ_PARTITION=tourbot_apriltag_77
export IGN_PARTITION=$GZ_PARTITION

docker compose -f docker_stuff/compose.yaml run --rm \
  --name tourbot-door-demo-gui \
  --no-deps dev bash -lc '
    source install/setup.bash
    export ROS_DOMAIN_ID=77
    export GZ_PARTITION=tourbot_apriltag_77
    export IGN_PARTITION=$GZ_PARTITION
    ros2 launch tourbot_bringup door_apriltag_gazebo_world_demo.launch.py \
      ros_domain_id:=77 \
      gz_partition:=tourbot_apriltag_77 \
      custom_gz_args:="-r -s --headless-rendering -v 2" \
      start_gazebo_gui:=true \
      gazebo_gui_command:="vglrun -d :0 gz sim -g -v 2" \
      start_image_view:=false
  '
```

如果容器内直连 X11 已能拿到 NVIDIA renderer，可以把 GUI 命令改为：

```bash
gazebo_gui_command:="gz sim -g -v 2"
```

判定依据是下面任一命令输出的 renderer 明确为 NVIDIA/RTX，而不是 llvmpipe/软件渲染：

```bash
docker compose -f docker_stuff/compose.yaml run --rm --no-deps dev bash -lc '
  source install/setup.bash
  glxinfo -B | grep -E "OpenGL vendor|OpenGL renderer" || true
  vglrun -d :0 glxinfo -B | grep -E "OpenGL vendor|OpenGL renderer" || true
'
```

2026-07-01 在 `xiao-5080` 实测：容器直连 GL 是 `llvmpipe`，`vglrun -d :0` 是 `NVIDIA GeForce RTX 5080/PCIe/SSE2`。因此本机推荐保留 `vglrun -d :0 gz sim -g -v 2` 作为独立 GUI client 命令。

说明：独立 GUI client 仍可能打印少量 `libEGL warning: egl: failed to create dri2 screen`。这与旧命令不同，警告只来自 GUI client，不再影响 headless server、controller 和穿门闭环。不要为了压这条日志强制设置 `QT_XCB_GL_INTEGRATION=xcb_glx`，实测会让 Gazebo `/clock` 异常，导致穿门阶段卡住。

退出方式：优先在启动 launch 的终端按一次 `Ctrl-C`，等待 ROS launch 自行回收各节点。2026-07-02 已修复本 demo 内 Python 节点在退出阶段的两个噪音来源：ROS context 失效后继续 publish stop cmd，以及重复 `rclpy.shutdown()`。如果仍看到 `gz sim` 在最后打印 `Segmentation fault (core dumped)`，这是 Gazebo GUI/server 进程的退出路径问题，不代表 AprilTag 开门/穿门闭环失败；以第 5 节成功判据为准。

GUI 中应能看到：

1. `cardboard_city` 3D world。
2. TurtleBot4 被设置到 tag 1 门前。
3. 外开门 tag 1 初始可见，贴在外开门门板朝向机器人一侧的表面。
4. demo 触发开门后，门板和 tag 被移动，tag 从 OAK-D 视野消失。
5. TurtleBot4 向前穿过门位。

## 3. Headless 一键模式

这是最稳定的回归命令：

```bash
cd ~/4sim/gh-ref/tour-guide-robot/Hyaxon-tour-guide-robot
export ROS_DOMAIN_ID=77
export GZ_PARTITION=tourbot_apriltag_77
export IGN_PARTITION=$GZ_PARTITION

docker compose -f docker_stuff/compose.yaml run --rm \
  --name tourbot-door-demo-headless \
  --no-deps dev bash -lc '
    source install/setup.bash
    export ROS_DOMAIN_ID=77
    export GZ_PARTITION=tourbot_apriltag_77
    export IGN_PARTITION=$GZ_PARTITION
    ros2 launch tourbot_bringup door_apriltag_gazebo_world_demo.launch.py \
      ros_domain_id:=77 \
      gz_partition:=tourbot_apriltag_77 \
      custom_gz_args:="-r -s --headless-rendering -v 2" \
      start_image_view:=false
  '
```

## 4. 两终端模式

两个终端必须使用同一组 `ROS_DOMAIN_ID` / `GZ_PARTITION`。

终端 A：启动 Gazebo 3D world + TurtleBot4。

```bash
cd ~/4sim/gh-ref/tour-guide-robot/Hyaxon-tour-guide-robot
export ROS_DOMAIN_ID=77
export GZ_PARTITION=tourbot_apriltag_77
export IGN_PARTITION=$GZ_PARTITION

docker compose -f docker_stuff/compose.yaml run --rm \
  --name tourbot-door-demo-sim \
  --no-deps dev bash -lc '
    source install/setup.bash
    export ROS_DOMAIN_ID=77
    export GZ_PARTITION=tourbot_apriltag_77
    export IGN_PARTITION=$GZ_PARTITION
    ros2 launch tourbot_bringup sim.launch.py \
      use_custom_sim:=true \
      start_navigation:=false \
      custom_gz_args:="-r -s --headless-rendering -v 2"
  '
```

终端 B：启动真实 Gazebo OAK-D AprilTag 门 demo。

```bash
cd ~/4sim/gh-ref/tour-guide-robot/Hyaxon-tour-guide-robot
export ROS_DOMAIN_ID=77
export GZ_PARTITION=tourbot_apriltag_77
export IGN_PARTITION=$GZ_PARTITION

docker compose -f docker_stuff/compose.yaml run --rm \
  --name tourbot-door-demo-node \
  --no-deps dev bash -lc '
    source install/setup.bash
    export ROS_DOMAIN_ID=77
    export GZ_PARTITION=tourbot_apriltag_77
    export IGN_PARTITION=$GZ_PARTITION
    ros2 launch tourbot_bringup door_apriltag_gazebo_demo.launch.py tag_id:=1
  '
```

终端 B 会自动设置机器人初始位姿，不需要手动运行 `gz service set_pose`。日志中应出现：

```text
gazebo_demo_initial_robot_pose]: Set Gazebo pose for turtlebot4.
```

## 5. 成功判据

无论用哪种入口，都必须看到下面这些日志，才算完整通过：

```text
Initial AprilTag 1 detection is available.
align_to_apriltag succeeded: Aligned to tag 1.
Applying Gazebo door state: open/tag hidden.
wait_for_tag_removed succeeded: Tag 1 removed from FOV
door_traverse succeeded: Door traversal complete for tag_id=1, door_type=OUTWARD
Door AprilTag demo complete: closed tag detected, tag removed, and door traversal finished.
```

如果卡在：

```text
Timed out waiting for initial detection of tag 1.
```

优先检查：

1. 是否同时残留了旧的 demo/sim 容器。
2. 两终端模式下终端 B 是否使用了同一个 `ROS_DOMAIN_ID` 和 `GZ_PARTITION`。
3. 终端 B 是否出现 `gazebo_demo_initial_robot_pose` 的 set pose 成功日志。
4. `/oakd/rgb/preview/image_raw` 和 `/oakd/rgb/preview/camera_info` 是否有消息。

如果看到：

```text
Ignoring the received message ... older than the current time ... exceeds the allowed timeout
```

说明 `diffdrive_controller` 丢弃了过期速度指令。当前 Gazebo door demo 已对 `/diffdrive_controller/cmd_vel` 使用 zero `TwistStamped` timestamp，让 controller 用自己的当前时刻接收命令；正常情况下最多只会看到一次：

```text
Received TwistStamped with zero timestamp, setting it to current time
```

这条一次性日志是可接受的。若仍持续出现 `Ignoring the received message`，优先确认没有使用旧的“整条 launch 外包 `vglrun` + `custom_gz_args:="-r -v 2"`”命令。

## 6. 运行中检查命令

另开一个终端进入同一个 ROS domain：

```bash
cd ~/4sim/gh-ref/tour-guide-robot/Hyaxon-tour-guide-robot
docker compose -f docker_stuff/compose.yaml run --rm --no-deps dev bash -lc '
  source install/setup.bash
  export ROS_DOMAIN_ID=77
  ros2 topic list | grep -E "oakd|detections|odom|cmd_vel"
'
```

检查 OAK-D 图像流：

```bash
docker compose -f docker_stuff/compose.yaml run --rm --no-deps dev bash -lc '
  source install/setup.bash
  export ROS_DOMAIN_ID=77
  timeout 8 ros2 topic hz /oakd/rgb/preview/image_raw
'
```

检查 AprilTag 检测：

```bash
docker compose -f docker_stuff/compose.yaml run --rm --no-deps dev bash -lc '
  source install/setup.bash
  export ROS_DOMAIN_ID=77
  timeout 8 ros2 topic echo /detections --once
'
```

检查穿门速度命令：

```bash
docker compose -f docker_stuff/compose.yaml run --rm --no-deps dev bash -lc '
  source install/setup.bash
  export ROS_DOMAIN_ID=77
  timeout 8 ros2 topic hz /diffdrive_controller/cmd_vel
'
```

检查里程计是否变化：

```bash
docker compose -f docker_stuff/compose.yaml run --rm --no-deps dev bash -lc '
  source install/setup.bash
  export ROS_DOMAIN_ID=77
  timeout 3 ros2 topic echo --once /odom
'
```

## 7. 清理

停止当前终端里的 launch 后，再确认没有残留临时容器：

```bash
docker ps --filter 'name=tourbot-door-demo-' --format 'table {{.ID}}\t{{.Names}}\t{{.Status}}'
```

如有残留：

```bash
docker ps -a --filter 'name=tourbot-door-demo-' --format '{{.ID}}' | xargs -r docker stop
docker ps -a --filter 'name=tourbot-door-demo-' --format '{{.ID}}' | xargs -r docker rm
```

确认是否产生 core 文件：

```bash
cd ~/4sim/gh-ref/tour-guide-robot/Hyaxon-tour-guide-robot
find . -maxdepth 3 \( -name 'core' -o -name 'core.*' \) -printf '%p %s\n'
```

如果只在退出时产生 `./core`，且第 5 节成功判据已经全部出现，优先按 Gazebo 退出崩溃处理；不要把它和 Python 节点 traceback 混在一起判断。需要保留现场时先不要删除 core。

## 8. 本次实测记录

2026-07-01 在 `xiao-5080` 验证：

- 两终端模式通过：
  - `gazebo_demo_initial_robot_pose` 成功设置 `turtlebot4` 位姿。
  - `Initial AprilTag 1 detection is available.`
  - `wait_for_tag_removed succeeded`
  - `door_traverse succeeded`
  - `Door AprilTag demo complete`
- Headless 一键模式通过：
  - `gazebo_initial_robot_pose` 成功设置 `turtlebot4` 位姿。
  - `apriltag_ros` 检测到 tag 1。
  - Gazebo door state 切换到 `open/tag hidden`。
  - `door_traverse` 完成 0.75 m 穿门。
  - 优化后实测 `elapsed_wall_s=128`，其中穿门阶段约 18 秒；`Ignoring the received message` 计数为 0，`failed to create dri2 screen` 计数为 0。
- GUI 建议使用 server/headless + 独立 GUI client 方式：
  - server 命令保持 `custom_gz_args:="-r -s --headless-rendering -v 2"`。
  - GUI client 由 `start_gazebo_gui:=true` 和 `gazebo_gui_command:="vglrun -d :0 gz sim -g -v 2"` 启动。
  - 不再推荐整条 `ros2 launch` 外包 `vglrun`，该方式可能让实时因子明显低于 1，并触发 controller 旧时间戳丢弃。
  - 优化 GUI 入口实测 `elapsed_wall_s=48`，完整日志到 `Door AprilTag demo complete`；`Ignoring the received message` 计数为 0，`zero timestamp` 仅出现一次 controller 提示。
  - 同一次 GUI 入口中仍有 2 条 `libEGL ... dri2`，来源是独立 GUI client；这次没有拖慢穿门，也没有导致旧速度指令丢弃。

注意：`turtlebot4_node` 偶尔会打印 `Service stop_motor unavailable`、`Service oakd/start_camera unavailable`，这来自 TurtleBot4 HMI/motion_control 层，不影响本 SOP 的 AprilTag 检测、开门和穿门成功判据。

2026-07-02 退出修复：`align_to_apriltag_server`、`door_behavior_server`、`wait_for_tag_removed_server`、`door_state_gazebo_controller`、`odom_tf_compat`、`nav2_post_localization_activator` 和 `door_apriltag_demo_node` 已改为幂等 shutdown；退出时 context 已失效就不再发布 stop cmd 或重复 `rclpy.shutdown()`。

2026-07-02 退出验证：使用独立 `ROS_DOMAIN_ID=177` / `GZ_PARTITION=tourbot_apriltag_exit_177` 运行 GUI 一键模式，日志出现 `door_traverse succeeded` 和 `Door AprilTag demo complete`。随后向 `ros2 launch` 发送 SIGINT，容器正常退出；日志没有 `Traceback`、`RCLError`、`failed to shutdown`、`publisher context is invalid` 或 `Segmentation fault`。退出阶段仍可能看到少量 `ros_gz_bridge` 的 `process has died`，这属于 Gazebo/bridge teardown 噪音，不是 Python 节点崩溃。

2026-07-02 边界修复后，`cardboard_city` 静态墙和纸箱障碍已补 collision。3D door demo 的默认 `door_forward_distance` 随之从 `0.75` 调整为 `0.60`，目标是清过门槛后停止，而不是把机器人推进到外围边界附近。`sim.launch.py` 已把 `custom_robot_x/y/z/yaw` 透传给 TurtleBot4 spawn，一键入口默认不再在 controller 启动后额外 teleport 机器人，并使用 `custom_spawn_with_create3_nodes:=false` 走项目内 `turtlebot4_door_demo_spawn.launch.py`，避免完整 TurtleBot4 spawn 自动生成的 `standard_dock` 和 Create3 `motion_control` 与门行为同时写 `/diffdrive_controller/cmd_vel`。`door_behavior_server` 也增加了可选 workspace/走廊 guard、最长运动时间、无进展 watchdog 和重复 stop 命令；这个一键 Gazebo demo 不把 diffdrive `/odom` 当作 Gazebo world 坐标，而是用 `/sim_ground_truth_pose` 驱动行为层的 workspace/走廊/进展判断。边界原因和验证方式见 `013-g55-apriltag-world-demo-faq.md` 的 Q12。

2026-07-02 tag 位置复核：`tag_id=1` 对应的 Gazebo 实体是 `apriltag_door_outward_1`。旧配置把它放在 `(3.14, -0.45, 0.45)`，与外开门门板中心 `(3.14, -0.53, 0.42)` 相差约 8 cm，所以从 GUI 顶视角看起来像门前/围栏边上独立漂着的 tag。现已把 tag 1 关闭态改为 `(3.14, -0.5115, 0.45)`，贴到外开门北侧门面；tag 2 也同步贴到内开门南侧门面 `(1.71, 0.5115, 0.45)`。`door_state_gazebo_controller.py` 的 closed pose 已同步，否则 demo 收到 `/door_demo/tag_visible=true` 时会把门 tag 再移回旧坐标。开门时仍按本 SOP 的 demo 逻辑把 tag 移到视野外，用来稳定触发 “tag removed from FOV”。

2026-07-02 tag 贴门后回归：使用独立 `ROS_DOMAIN_ID=188` / `GZ_PARTITION=tourbot_apriltag_tagfix_188` 跑 headless 一键模式，日志依次出现 `Initial AprilTag 1 detection is available`、`align_to_apriltag succeeded`、`Applying Gazebo door state: open/tag hidden`、`wait_for_tag_removed succeeded`、`door_traverse succeeded` 和 `Door AprilTag demo complete`。本次验证命令外层使用 110 秒 timeout；成功日志出现后 launch 继续常驻，最终 timeout 返回 `124`，不代表 demo 失败。

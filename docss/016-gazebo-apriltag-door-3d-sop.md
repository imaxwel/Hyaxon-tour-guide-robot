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

- GUI 一键模式：打开 Gazebo 3D 界面，适合人工观察。
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
    tourbot_bringup tourbot_mission tourbot_perception
'
```

## 2. GUI 一键模式

在 `xiao-5080` 桌面环境的终端运行。该模式会打开 Gazebo 3D 界面；如果通过纯 SSH 且没有 X11/VirtualGL，会优先使用第 3 节 headless 模式。

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
    vglrun -d :0 ros2 launch tourbot_bringup door_apriltag_gazebo_world_demo.launch.py \
      ros_domain_id:=77 \
      gz_partition:=tourbot_apriltag_77 \
      custom_gz_args:="-r -v 2" \
      start_image_view:=false
  '
```

GUI 中应能看到：

1. `cardboard_city` 3D world。
2. TurtleBot4 被设置到 tag 1 门前。
3. 外开门 tag 初始可见。
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

确认没有 core 文件：

```bash
cd ~/4sim/gh-ref/tour-guide-robot/Hyaxon-tour-guide-robot
find . -maxdepth 3 \( -name 'core' -o -name 'core.*' \) -printf '%p %s\n'
```

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

注意：`turtlebot4_node` 偶尔会打印 `Service stop_motor unavailable`、`Service oakd/start_camera unavailable`，这来自 TurtleBot4 HMI/motion_control 层，不影响本 SOP 的 AprilTag 检测、开门和穿门成功判据。

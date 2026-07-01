# 012 · G55 AprilTag world 补全与门流程演示

> 日期：2026-06-30  
> 目标：在 `cardboard_city` 仿真 world 中补齐 AprilTag 资产，并提供可重复的“门 tag 可见 = 门关闭、tag 消失 = 门打开、随后穿门”演示入口。

## 1.本次补齐内容

### 1.1 生成 8 个 AprilTag 36h11 模型

模型目录：

```text
src/tourbot_bringup/worlds/cardboard_city/models/
  tag36_11_00000/
  tag36_11_00001/
  ...
  tag36_11_00007/
```

每个模型包含：

```text
model.sdf
model.config
materials/textures/tag36_11_XXXXX.png
thumbnails/tag36_11_XXXXX.png
```

关键约束：

- SDF 版本：`1.9`
- 物理边长：`0.162 m`
- tag family：`36h11`
- 纹理来源：`AprilRobotics/apriltag-imgs`

这与当前配置保持一致：

```text
src/tourbot_perception/config/apriltags_36h11.yaml
family: 36h11
size: 0.162
```

### 1.2 include 到 `world.sdf`

修改文件：

```text
src/tourbot_bringup/worlds/cardboard_city/world.sdf
```

已加入：

- `apriltag_home_0`
- `apriltag_door_outward_1`
- `apriltag_door_inward_2`
- `apriltag_goal_3`
- `apriltag_goal_4`
- `apriltag_goal_5`
- `apriltag_goal_6`
- `apriltag_goal_7`

摆放原则：

- `landmarks.yaml` 中的坐标按“机器人观察 pose”处理。
- tag 放在观察 pose 前方约 `0.45 m`。
- tag 法线朝向机器人。
- 门板、纸箱、边界墙先做视觉几何，不加碰撞，避免开环穿门动作被静态门板挡住。

## 2.修复 custom world 启动方式

原问题：

TurtleBot4 下游 launch 会把 `world` 参数同时当作：

- Gazebo 要加载的 world 文件名；
- ROS-GZ bridge topic 中的 world name。

如果直接传绝对路径，会生成非法 topic，例如：

```text
/world//ws/install/.../world/model/turtlebot4/...
```

这会导致 `ros_gz_bridge` 解析 remap rule 失败。

当前修复：

- `tourbot_bringup/launch/sim.launch.py` 的 custom 分支改为直接启动 `ros_gz_sim`，用绝对 SDF 路径加载 world。
- TurtleBot4 spawn / bridge 使用合法 world name：`world_demo`。
- 增加 `custom_world_name` 参数。
- 增加 `custom_gz_args` 参数。
- 增加 `start_navigation` 参数，默认 `true`；门 demo 时建议设为 `false`。
- 自动设置 `GZ_SIM_RESOURCE_PATH` / `IGN_GAZEBO_RESOURCE_PATH`，让 Gazebo 能找到 `models/tag36_11_00000..00007`。

## 3.稳定门流程 demo

新增 launch：

```text
src/tourbot_bringup/launch/door_apriltag_demo.launch.py
```

新增节点：

```text
src/tourbot_mission/tourbot_mission/door_apriltag_demo_node.py
```

它会启动并驱动现有三个 action server：

- `/align_to_apriltag`
- `/wait_for_tag_removed`
- `/door_traverse`

演示逻辑：

1. 发布 `/oakd/rgb/preview/camera_info`。
2. 发布 `/detections`，让门 tag `tag_id=1` 可见，表示门关闭。
3. 调用 `/align_to_apriltag`，对齐到 tag。
4. 调用 `/wait_for_tag_removed`，先保持 tag 可见 `2.0s`，再停止发布该 tag，表示门打开。
5. 调用 `/door_traverse`，执行穿门。

为了让演示不受 Gazebo controller 抖动影响，demo launch 中的 `door_behavior_server` 使用 `/door_demo/odom`，由 demo 节点根据 `/cmd_vel` 积分发布。真实 `mission.launch.py` 不受影响，仍使用真实/仿真 `/odom`。

## 4.运行命令

推荐两个终端，使用同一个 `ROS_DOMAIN_ID`。下面用 `77` 避免和已有仿真串话。

终端 A：启动 custom world + TurtleBot4，不启动 Nav2/RViz。

`use_custom_sim:=true` 的默认 `custom_world` 现在指向：

```text
/ws/install/tourbot_bringup/share/tourbot_bringup/worlds/cardboard_city/world_no_sensors.sdf
```

这个 world 保留 AprilTag / 门 / 纸箱视觉资产，但不加载 `gz-sim-sensors-system`。当前门 demo 使用可控 `/detections`，不依赖 Gazebo 相机或雷达渲染，因此该配置更适合 headless Docker 启动。

```bash
cd ~/4sim/gh-ref/tour-guide-robot/Hyaxon-tour-guide-robot
docker compose -f docker_stuff/compose.yaml run --rm --no-deps dev bash -lc '
  source install/setup.bash
  export ROS_DOMAIN_ID=77
  export GZ_PARTITION=tourbot_apriltag_77
  export IGN_PARTITION=$GZ_PARTITION
  ros2 launch tourbot_bringup sim.launch.py \
    use_custom_sim:=true \
    start_navigation:=false \
    custom_gz_args:="-r -s -v 2"
'
```

终端 B：启动门 AprilTag demo。

```bash
cd ~/4sim/gh-ref/tour-guide-robot/Hyaxon-tour-guide-robot
docker compose -f docker_stuff/compose.yaml run --rm --no-deps dev bash -lc '
  source install/setup.bash
  export ROS_DOMAIN_ID=77
  ros2 launch tourbot_bringup door_apriltag_demo.launch.py tag_id:=1
'
```

### 4.1 UI 视觉闭环 demo

如果需要直观看到门 / tag / 检测框，不要再启动上面的“终端 B”。改用下面这个视觉闭环入口作为新的终端 B：

```bash
cd ~/4sim/gh-ref/tour-guide-robot/Hyaxon-tour-guide-robot
docker compose -f docker_stuff/compose.yaml run --rm --no-deps dev bash -lc '
  source install/setup.bash
  export ROS_DOMAIN_ID=77
  export GZ_PARTITION=tourbot_apriltag_77
  export IGN_PARTITION=$GZ_PARTITION
  ros2 launch tourbot_bringup door_apriltag_visual_demo.launch.py \
    tag_id:=1 \
    start_image_view:=true
'
```

该 launch 会启动：

- `door_visual_camera_node`：发布 `/oakd/rgb/preview/image_raw`、`/oakd/rgb/preview/camera_info` 和带叠加信息的 `/door_demo/visualization/image_raw`。
- `apriltag_ros`：从图像真实检测 AprilTag，并发布 `/detections`。
- 原来的三个 action server：`/align_to_apriltag`、`/wait_for_tag_removed`、`/door_traverse`。
- `image_view`：打开 UI 窗口显示 `/door_demo/visualization/image_raw`。

视觉闭环路径是：

```text
visual camera image -> apriltag_ros -> /detections -> align_to_apriltag -> wait_for_tag_removed -> door_traverse
```

窗口中的预期现象：

1. 初始显示 `DOOR CLOSED - tag visible`，画面中央有 AprilTag。
2. `apriltag_ros /detections ids=[1]`，并在 tag 上画绿色检测框。
3. demo 触发开门后显示 `DOOR OPEN - tag removed`，检测列表变成 `ids=[]`。
4. 随后日志打印 `door_traverse succeeded` 和 `Door AprilTag demo complete`。

预期关键日志：

```text
align_to_apriltag succeeded: Aligned to tag 1.
Door is CLOSED: publishing visible AprilTag 1 for 2.0s.
Door is OPEN: AprilTag is no longer visible.
wait_for_tag_removed succeeded: Tag 1 removed from FOV for 1.55 seconds.
door_traverse succeeded: Door traversal complete for tag_id=1, door_type=OUTWARD
Door AprilTag demo complete: closed tag detected, tag removed, and door traversal finished.
```

### 4.2 真实 Gazebo OAK-D 3D 闭环 demo

在 015 文档修复 Gazebo OGRE1/OGRE2 渲染插件冲突后，已补齐完整 Gazebo 3D 闭环入口：

```text
Gazebo world + TurtleBot4 OAK-D rgbd_camera
  -> ros_gz_bridge
  -> /oakd/rgb/preview/image_raw + /oakd/rgb/preview/camera_info
  -> apriltag_ros
  -> /detections
  -> align_to_apriltag
  -> wait_for_tag_removed
  -> Gazebo set_pose 开门/隐藏 tag
  -> door_traverse 通过 /odom + diffdrive_controller 穿门
```

新增文件：

```text
src/tourbot_bringup/launch/door_apriltag_gazebo_world_demo.launch.py
src/tourbot_bringup/launch/door_apriltag_gazebo_demo.launch.py
src/tourbot_bringup/tourbot_bringup/door_state_gazebo_controller.py
src/tourbot_bringup/tourbot_bringup/gazebo_entity_pose_setter.py
src/tourbot_perception/config/apriltags_36h11_gazebo.yaml
```

一键运行：

```bash
cd ~/4sim/gh-ref/tour-guide-robot/Hyaxon-tour-guide-robot
docker compose -f docker_stuff/compose.yaml run --rm --no-deps dev bash -lc '
  source install/setup.bash
  export ROS_DOMAIN_ID=77
  export GZ_PARTITION=tourbot_apriltag_77
  export IGN_PARTITION=$GZ_PARTITION
  ros2 launch tourbot_bringup door_apriltag_gazebo_world_demo.launch.py \
    ros_domain_id:=77 \
    gz_partition:=tourbot_apriltag_77 \
    custom_gz_args:="-r -s --headless-rendering -v 2"
'
```

两终端运行：

终端 A：启动 custom world + TurtleBot4。

```bash
cd ~/4sim/gh-ref/tour-guide-robot/Hyaxon-tour-guide-robot
docker compose -f docker_stuff/compose.yaml run --rm --no-deps dev bash -lc '
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

终端 B：启动真实 Gazebo OAK-D AprilTag/门行为闭环。

```bash
cd ~/4sim/gh-ref/tour-guide-robot/Hyaxon-tour-guide-robot
docker compose -f docker_stuff/compose.yaml run --rm --no-deps dev bash -lc '
  source install/setup.bash
  export ROS_DOMAIN_ID=77
  export GZ_PARTITION=tourbot_apriltag_77
  export IGN_PARTITION=$GZ_PARTITION
  ros2 launch tourbot_bringup door_apriltag_gazebo_demo.launch.py tag_id:=1
'
```

`door_apriltag_gazebo_demo.launch.py` 默认会启动 `gazebo_entity_pose_setter`，把已经运行的 `turtlebot4` 设置到 tag 1 门前观察位。因此两终端模式下不需要手动调用 `gz service set_pose`。

关键实现点：

- `world_no_sensors.sdf` 继续作为默认 world，避免 world 级 sensors-system 与 TurtleBot4 robot model 自带 sensors-system 重复。
- `apriltags_36h11_gazebo.yaml` 使用 `qos_profile: sensor_data`、`max_hamming: 2`、`detector.decimate: 1.0`，适配 Gazebo 渲染出来的 tag 图像质量。
- `door_state_gazebo_controller` 订阅 `/door_demo/tag_visible`，通过 Gazebo `/world/world_demo/set_pose` 移动门板和 tag：可见时门关闭，隐藏时门打开。
- `gazebo_entity_pose_setter` 在 spawn 后把 `turtlebot4` 设置到 tag 1 观察位。TurtleBot4 spawn launch 的 x/y/yaw 参数在当前栈里不稳定，demo 不再依赖它们直接生效。
- Gazebo demo 的速度命令走 `/diffdrive_controller/cmd_vel`，里程计使用真实 `/odom`，不再使用 `/door_demo/odom` 积分替身。
- Gazebo demo 的门状态控制、mission 控制流和 door behavior 使用 wall time；mission 节点在状态切换点主动重复发布 `/door_demo/tag_visible`，避免 `/clock` 暂时缺失时 ROS timer 不触发。

## 5.验证结果

已在远端 `xiao-5080` 的 Docker 环境验证：

- `colcon build --symlink-install --packages-select tourbot_bringup tourbot_mission` 通过。
- `sim.launch.py use_custom_sim:=true start_navigation:=false custom_gz_args:="-r -s -v 2"` 默认加载 `world_no_sensors.sdf`，能启动 `world_demo`，并创建合法 `/world/world_demo/...` bridge。
- `joint_state_broadcaster` 与 `diffdrive_controller` 能正常 load / configure / activate；原先由 Gazebo 先崩溃导致的 controller spawner 超时不再出现。
- `/odom` 在 2 秒内出现。
- `door_apriltag_demo.launch.py tag_id:=1` 在约 15 秒内打印完整成功日志；launch 内的 action servers 会继续驻留，测试脚本用 `timeout` / Ctrl-C 结束时会出现正常清理日志。
- `door_apriltag_visual_demo.launch.py tag_id:=1 start_image_view:=false` 已验证可由 `apriltag_ros` 从 `/oakd/rgb/preview/image_raw` 检测出 tag，并完成同一套门行为链路。
- `door_apriltag_gazebo_world_demo.launch.py` 已验证完整真实 Gazebo OAK-D 3D 闭环：
  - `gazebo_entity_pose_setter` 成功把 `turtlebot4` 设置到 tag 1 观察位。
  - `apriltag_ros` 从 Gazebo `/oakd/rgb/preview/image_raw` 检测到 `tag_id=1`。
  - `door_state_gazebo_controller` 收到 closed/open 状态并移动 Gazebo tag/门板。
  - `wait_for_tag_removed` 在 tag 移出视野后成功。
  - `door_behavior_server` 通过 `/diffdrive_controller/cmd_vel` + `/odom` 完成 `0.75 m` 穿门动作。
  - 最终日志：`Door AprilTag demo complete: closed tag detected, tag removed, and door traversal finished.`

## 6.分层说明

当前保留三层入口，便于不同风险级别的回归：

- `door_apriltag_demo.launch.py`：最稳定的行为链路回归，使用可控 `/detections` 和 `/door_demo/odom`。
- `door_apriltag_visual_demo.launch.py`：独立 ROS camera publisher 生成图像，由 `apriltag_ros` 做真实图像检测，不依赖 Gazebo render sensors。
- `door_apriltag_gazebo_world_demo.launch.py` / `door_apriltag_gazebo_demo.launch.py`：真实 Gazebo OAK-D 3D 闭环，使用 Gazebo 相机图像、真实 `/odom` 和 `diffdrive_controller`。

注意：

- 默认仍使用 `world_no_sensors.sdf`。这不是“无相机”，而是去掉 world 级 sensors-system，让 TurtleBot4 robot model 自带的 OAK-D sensors-system 唯一生效。
- `world.sdf` 也同步了独立门板模型，方便 `set_pose` 控制，但 full world 仍不推荐作为默认入口。
- 如果 apt upgrade 或重建基础镜像后 OGRE1 插件文件恢复，需要按 015 文档重新构建 Dockerfile 修复层。
- 完整 3D GUI/headless 操作 SOP 见 `docss/016-gazebo-apriltag-door-3d-sop.md`。

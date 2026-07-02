# 013 · G55 AprilTag world demo FAQ

> 日期：2026-07-02
> 主机：`xiao-5080` / Ubuntu 24.04 / ROS 2 Jazzy / Gazebo Harmonic / RTX 5080 Docker 环境

## Q1：为什么按 012 的命令启动会报 `exit code 139`？

根因不是 ROS 2 controller 本身，而是 Gazebo 先崩溃了。

原 full-sensors world 加载了：

```xml
<plugin filename="gz-sim-sensors-system"
    name="gz::sim::systems::Sensors">
    <render_engine>ogre2</render_engine>
</plugin>
```

在 `xiao-5080` 当前容器环境里，`gz sim -s` 的服务端 Sensors 渲染线程会进入 OGRE2 / EGL 路径并崩溃。典型日志是：

```text
libEGL warning: pci id ... 10de:2c02, driver (null)
libEGL warning: egl: failed to create dri2 screen
gz::sim::v8::systems::SensorsPrivate::RenderThread()
gz::rendering::v8::Ogre2Node::AttachChild(...)
Segmentation fault
[ERROR] [gazebo-1]: process has died [... exit code 139 ...]
```

Gazebo 死掉后，`/controller_manager/*` 服务也随之不可用，所以后面的：

```text
spawner_joint_state_broadcaster: Failed getting a result
spawner_diffdrive_controller: Could not contact service /controller_manager/list_controllers
```

只是连锁错误。

## Q2：哪些日志不是这次故障的根因？

下面这些在当前问题里不是根因：

- `KDL does not support a root link with an inertia`：URDF/KDL 警告，不会导致 Gazebo 139。
- `Desired controller update period (0.001 s) is faster than the gazebo simulation period (0.003 s)`：controller 周期配置警告，full-sensors 崩溃前后都会出现。
- `Gazebo does not support Ogre material scripts`：材质兼容警告，不是直接崩溃点。
- controller spawner 超时：Gazebo 已经退出后的结果，不是第一现场。

## Q3：已经尝试过哪些方向？

在 `xiao-5080` 上做过这些排查：

- `vglrun -d :0 glxinfo -B` 能看到 RTX 5080，但把 launch 包在 `vglrun` 里不能修复 `gz sim -s` 的服务端 EGL 渲染崩溃。
- 强制 `__EGL_VENDOR_LIBRARY_FILENAMES=/usr/share/glvnd/egl_vendor.d/10_nvidia.json` 可以让 `eglinfo` 走 NVIDIA，但 full-sensors world 仍在 Sensors render thread 崩溃。
- `LIBGL_ALWAYS_SOFTWARE=1` 不适合该路径，EGL 会拒绝强制软件渲染硬件 device。
- 临时删除 AprilTag include 后仍会崩溃，所以不是 tag 纹理本身导致。
- 切换 `--render-engine-server ogre` 会避开原 OGRE2 栈，但会触发 OGRE1 相关 abort，不是可用修复。

## Q4：当前修复是什么？

新增了：

```text
src/tourbot_bringup/worlds/cardboard_city/world_no_sensors.sdf
```

它保留 `cardboard_city` 的地面、门、纸箱、墙体和 8 个 AprilTag 可视模型，但不加载 `gz-sim-sensors-system`。

同时 `sim.launch.py` 的 `use_custom_sim:=true` 默认 `custom_world` 已改为：

```text
worlds/cardboard_city/world_no_sensors
```

因此 012 里的 Terminal A 命令可以继续这样启动：

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

## Q5：为什么门 demo 可以不用 Gazebo Sensors？

012 的稳定门流程 demo 验证的是行为链路：

```text
/detections -> align_to_apriltag -> wait_for_tag_removed -> door_traverse
```

其中 `/detections` 由 `door_apriltag_demo.launch.py` 内的 demo 节点可控发布，用来表达：

- tag 可见：门关闭；
- tag 消失：门打开；
- 然后执行穿门动作。

所以这个 demo 不依赖 Gazebo OAK-D 相机真实识别 AprilTag，也不依赖 Gazebo lidar / depth rendering。禁用 `gz-sim-sensors-system` 不影响该行为链路验证。

## Q6：如果我要做真实 Gazebo 相机识别 AprilTag 怎么办？

显式恢复 full-sensors world：

```bash
custom_world:=/ws/install/tourbot_bringup/share/tourbot_bringup/worlds/cardboard_city/world
```

但这会重新加载 `gz-sim-sensors-system`，在当前 `xiao-5080` 环境里仍可能复现 OGRE2/EGL 崩溃。真实视觉闭环需要作为下一层集成单独处理：

- 固定 Gazebo Harmonic / gz-rendering / NVIDIA driver / container runtime 版本组合；
- 单独验证 `gz sim -s` server-side render sensors；
- 再接入 OAK-D image topic 与 `apriltag_ros`；
- 最后确认 `/detections` 来自真实图像，而不是 demo synthetic publisher。

## Q7：`ROS_DOMAIN_ID` 能隔离所有仿真吗？

不能。`ROS_DOMAIN_ID` 只隔离 ROS 2 DDS 通信，不隔离 Gazebo Transport。

在同一台机器上多开 Gazebo 时，建议同时设置：

```bash
export ROS_DOMAIN_ID=77
export GZ_PARTITION=tourbot_apriltag_77
export IGN_PARTITION=$GZ_PARTITION
```

这能减少 Gazebo world / service / topic 串话。

## Q8：看到 `groups: cannot find name for group ID 1010` 要处理吗？

这只是容器内用户组 ID 没有名字的提示，不是本次 Gazebo crash 的原因。只要文件权限和 Docker 设备挂载正常，可以暂时忽略。

## Q9：如何判断修复后的启动是正常的？

Terminal A 中应能看到：

```text
Entity creation successful.
Resource Manager has been successfully initialized.
Loaded joint_state_broadcaster
Configured and activated joint_state_broadcaster
Loaded diffdrive_controller
Configured and activated diffdrive_controller
```

不应在启动阶段看到：

```text
[ERROR] [gazebo-1]: process has died [... exit code 139 ...]
```

测试脚本用 `timeout` 或手动 Ctrl-C 中断时，ROS launch 可能打印若干 `KeyboardInterrupt`、`exit code -2` 或清理阶段日志；这和启动阶段的 Gazebo 139 崩溃不是同一类问题。

## Q10：为什么 Terminal B 的 door demo 成功后 `timeout` 仍返回 124？

`door_apriltag_demo.launch.py` 会启动 demo node，也会同时启动几个 action server。demo node 打印完成后，action servers 仍会驻留等待后续请求，因此整个 launch 不会自动退出。

判断成功看这些日志：

```text
align_to_apriltag succeeded
wait_for_tag_removed succeeded
door_traverse succeeded
Door AprilTag demo complete
```

如果用 `timeout` 或 Ctrl-C 结束 Terminal B，后面的 `KeyboardInterrupt`、`publisher's context is invalid`、`exit code -2` 属于清理阶段噪声，不表示门流程失败。

## Q11：如何获得 UI 界面的直观可视化结果？

不要把 UI 闭环建在 Gazebo `gz-sim-sensors-system` 上；在 `xiao-5080` 当前环境里，即使加 `--headless-rendering`，full-sensors world 仍会在 Gazebo Sensors render thread 里 139。

当前实现的可视化闭环入口是：

```bash
ros2 launch tourbot_bringup door_apriltag_visual_demo.launch.py \
  tag_id:=1 \
  start_image_view:=true
```

它会打开 `image_view` 窗口显示：

```text
/door_demo/visualization/image_raw
```

同时内部链路是：

```text
/oakd/rgb/preview/image_raw
  -> apriltag_ros
  -> /detections
  -> /align_to_apriltag
  -> /wait_for_tag_removed
  -> /door_traverse
```

也就是说，`/detections` 不再由 demo 节点直接伪造，而是由 `apriltag_ros` 对图像流真实检测得到。UI 画面会显示 `DOOR CLOSED - tag visible`、检测框、`ids=[1]`，开门后显示 `DOOR OPEN - tag removed`、`ids=[]`。

如果只是自动化验证，不想弹出窗口：

```bash
ros2 launch tourbot_bringup door_apriltag_visual_demo.launch.py \
  tag_id:=1 \
  start_image_view:=false
```

注意：这个 visual launch 已经包含 action servers 和 demo node，不能和旧的 `door_apriltag_demo.launch.py` 在同一 `ROS_DOMAIN_ID` 里同时运行。

## Q12：为什么 3D door demo 穿门后像是不考虑 cardboard_city 边界，还会沿外围右侧继续走？

这是两个层面的约束缺失叠加造成的。

第一层是 Gazebo 物理世界。原 `cardboard_city` 的墙、门板和纸箱只建了 `<visual>`，没有对应 `<collision>`。Gazebo 只用 collision 做物理接触，视觉墙只是给人看的，因此机器人不会被边界墙挡住。相关旧注释也明确写过这些 cardboard panels 是 visual-only。

第二层是控制闭环。`016-gazebo-apriltag-door-3d-sop` 的 3D door demo 为了隔离门识别/开门/穿门链路，启动 world 时使用：

```text
start_navigation:=false
```

穿门阶段由 `door_behavior_server` 直接向 `/diffdrive_controller/cmd_vel` 发布速度，不经过 Nav2 的 global/local costmap、planner、controller 或 collision monitor。旧实现只按 `/odom` 的欧氏距离执行“直线走固定距离”，没有穿门走廊、最长运动时间或无进展 watchdog。因此只要初始姿态、里程计或观察角度有偏差，行为层也不会主动判断“已经偏离穿门走廊/撞墙后没有继续前进”。

当前修复分两层：

- `src/tourbot_bringup/worlds/cardboard_city/world.sdf`
- `src/tourbot_bringup/worlds/cardboard_city/world_no_sensors.sdf`

这两个 world 已新增 `cardboard_city_static_collisions`，给四周边界墙和纸箱障碍补了 matching collision，让 Gazebo 物理边界与可视边界一致。门板仍保持 visual-only，因为当前 demo 用 Gazebo `set_pose` 模拟开门；带 collision 的真实门应作为后续 SITL/高保真模型，用 joint、limit、damping 和随门状态变化的 collision 单独实现。

同时 `door_behavior_server` 已新增行为层保护，并在 `door_apriltag_gazebo_demo.launch.py` 中为 3D demo 使用 Gazebo ground-truth 位姿打开 workspace、走廊和进展 guard：

```text
odom_topic: /sim_ground_truth_pose
enforce_workspace_bounds: true
workspace_min_x: -0.45
workspace_max_x: 4.15
workspace_min_y: -1.20
workspace_max_y: 1.20
max_lateral_drift: 0.35
max_linear_motion_sec: 90.0
linear_stall_timeout_sec: 20.0
linear_stall_min_progress: 0.01
stop_command_repeats: 8
stop_command_period_sec: 0.05
```

注意：`/odom` 仍应按局部里程计处理，不应默认假设它就是 Gazebo world/map 坐标。这个 Gazebo door demo 已把 `door_behavior_server` 的 `odom_topic` 改为 `/sim_ground_truth_pose`，该话题由 Gazebo pose republisher 输出，坐标系是 `world_demo`，因此可以启用绝对 workspace guard 和基于 yaw 的穿门走廊 guard。真实机器人或 Nav2 场景不要直接照搬这个 ground-truth topic；应使用 map/world 对齐后的定位输入。

一键 `door_apriltag_gazebo_world_demo.launch.py` 还修正了机器人初始位姿设置方式：`sim.launch.py` 现在会把 `custom_robot_x/y/z/yaw` 透传给 TurtleBot4 spawn，一键入口默认不再在 controller 已启动后额外 `set_pose`。运行后 teleport 会让 Gazebo world pose 和 diffdrive `/odom` 更容易拉开，是这类 demo 中应避免的做法。由于完整 TurtleBot4 spawn 会同时生成 `standard_dock` 并启动 Create3 `motion_control`，它会在 docked/接触/reflex 状态下向 `/diffdrive_controller/cmd_vel` 发布反向旋转命令；这和本 SOP 的低层门行为直控底盘会形成两个控制源竞争。因此一键入口会给 `sim.launch.py` 传 `custom_spawn_with_create3_nodes:=false`，使用项目内 `turtlebot4_door_demo_spawn.launch.py`：只生成 TurtleBot4、bridge、ros2_control、ground-truth/sensor republisher 和必要 TF，不生成 dock，也不启动 `motion_control`。两终端模式仍可由 `door_apriltag_gazebo_demo.launch.py` 执行一次 pose reset，因为终端 A 的通用 sim 命令默认不指定门前位姿；若终端 A 使用完整 TurtleBot4 spawn，则不应再让门行为和 `motion_control` 同时写底层 cmd_vel。

3D demo 的默认 `door_forward_distance` 也从原先的 `0.75` 调整为 `0.60`。原因是补上真实静态 collision 后，穿门动作应只清过门槛，不应把机器人推进到外围墙附近。

修复后的正常启动日志里应看到：

```text
Linear motion timeout enabled: max_linear_motion_sec=90.0 s.
Linear stall guard enabled: timeout=20.0 s, min_progress=0.010 m.
Repeated stop commands enabled: count=8, period=0.05 s.
```

如果机器人被新加的物理边界挡住后不再产生有效里程计进展，预期行为不再是一直向边界发速度，而是停止并让 `/door_traverse` 失败，日志类似：

```text
Door traversal made no progress for 20.0 seconds (distance=... m, target=... m)
```

如果在位姿/航向坐标正确对齐的场景中启用了走廊 guard，也可能看到：

```text
Door traversal left the allowed corridor: lateral_drift=... m, limit=... m
```

如果启用了绝对 workspace guard，并且所用位姿确实是全局 workspace/map/world 坐标，也可能看到：

```text
Door traversal stopped at workspace boundary: pose=(..., ...), bounds=...
```

验证时继续使用 016 的一键命令即可。成功判据仍是：

```text
door_traverse succeeded: Door traversal complete for tag_id=1, door_type=OUTWARD
Door AprilTag demo complete: closed tag detected, tag removed, and door traversal finished.
```

如果故意测试行为层保护，可以把初始位姿或朝向调到会撞上静态墙的位置。此时 demo 应由无进展 watchdog 停止并失败，这说明行为层保护生效；不要把这种失败当成 AprilTag 或 Gazebo 相机识别问题。

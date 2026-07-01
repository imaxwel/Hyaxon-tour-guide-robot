# 013 · G55 AprilTag world demo FAQ

> 日期：2026-07-01  
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

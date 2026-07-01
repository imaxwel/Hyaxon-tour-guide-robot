# 014 · Gazebo 3D AprilTag door demo plan

> 日期：2026-07-01  
> 主机：`xiao-5080`  
> 目标：解释当前 custom world / UI 现状，并规划在 Gazebo 3D 场景中完成 AprilTag 感知、开门、穿门动作的行业最佳实践路线。

## 1. 结论先行

当前 Terminal A 用的不是 warehouse world，而是本仓库的 custom world：

```text
src/tourbot_bringup/worlds/cardboard_city/world_no_sensors.sdf
```

安装后路径是：

```text
/ws/install/tourbot_bringup/share/tourbot_bringup/worlds/cardboard_city/world_no_sensors.sdf
```

它来自：

```text
src/tourbot_bringup/worlds/cardboard_city/world.sdf
```

区别是 `world_no_sensors.sdf` 删除了 Gazebo 的 render sensor system：

```xml
<plugin filename="gz-sim-sensors-system"
    name="gz::sim::systems::Sensors">
    <render_engine>ogre2</render_engine>
</plugin>
```

所以它仍然有 3D world 几何、门板、墙体、纸箱、8 个 AprilTag 模型和 TurtleBot4，但不会产生 Gazebo 相机 / lidar / depth 图像。

当前命令里还有：

```bash
custom_gz_args:="-r -s -v 2"
```

其中 `-s` 是 server-only。也就是说，即使 world 是 3D 的，也不会打开 Gazebo GUI。要看到 Gazebo 3D 场景，Terminal A 需要去掉 `-s`，例如：

```bash
custom_gz_args:="-r -v 2"
```

但这只能解决“看到 3D 场景”的问题，不能自动解决“Gazebo 相机真实视觉闭环”。完整 Gazebo camera 闭环当前被 `gz-sim-sensors-system` 在 RTX 5080 容器环境下的 OGRE2/EGL 崩溃阻塞。

## 2. 当前项目现状

### 2.1 已经具备的能力

项目现在已经有这些可复用基础：

- 3D world：`cardboard_city/world.sdf` 和 `world_no_sensors.sdf`。
- 8 个 AprilTag 36h11 模型：`tag36_11_00000` 到 `tag36_11_00007`。
- 门 tag：`tag_id=1` outward door，`tag_id=2` inward door。
- TurtleBot4 custom sim spawn：`tourbot_bringup/launch/sim.launch.py`。
- AprilTag pipeline：`tourbot_perception/launch/apriltag_pipeline.launch.py`，订阅 `/oakd/rgb/preview/image_raw` 和 `/oakd/rgb/preview/camera_info`，发布 `/detections`。
- 行为 action servers：
  - `/align_to_apriltag`
  - `/wait_for_tag_removed`
  - `/door_traverse`
- 稳定行为级 demo：`door_apriltag_demo.launch.py`。
- ROS 级视觉闭环 demo：`door_apriltag_visual_demo.launch.py`，由 ROS camera publisher 生成图像，`apriltag_ros` 真实检测图像，再驱动门行为。

### 2.2 当前不是 3D Gazebo 闭环的原因

现在看到的是 2D 示意 UI，因为 `door_apriltag_visual_demo.launch.py` 有意绕开了 Gazebo render sensors：

```text
door_visual_camera_node -> /oakd/rgb/preview/image_raw
apriltag_ros -> /detections
behavior actions -> /cmd_vel
image_view -> /door_demo/visualization/image_raw
```

这样做的原因不是项目不想用 Gazebo 3D，而是当前 full-sensors world 在 `xiao-5080` 上已验证会崩溃：

```text
gz::sim::v8::systems::SensorsPrivate::RenderThread()
gz::rendering::v8::Ogre2Node::AttachChild(...)
Segmentation fault
[ERROR] [gazebo-1]: process has died [... exit code 139 ...]
```

即使使用：

```bash
--headless-rendering
```

仍然会在 `gz-sim-sensors-system` 的 render thread 里 139。

## 3. 能否在 Gazebo 3D 场景里做 AprilTag 穿门动作？

可以，但要分清三种层级。

### 3.1 Level 1：3D 场景可视化 + 行为级闭环

这是最近、风险最低的路线。

做法：

- Terminal A 用 `world_no_sensors.sdf`。
- 去掉 `-s`，打开 Gazebo GUI。
- Terminal B 继续使用 synthetic detections 或 ROS visual detections。
- Robot 的 `/cmd_vel` 仍进入 Gazebo，TurtleBot4 能在 3D world 中运动。
- AprilTag 检测事件不来自 Gazebo 相机，而来自可控 ROS 节点。

优点：

- 不依赖当前会崩溃的 Gazebo render sensors。
- 可以在 Gazebo 3D 场景里看到 TurtleBot4 运动、对齐、穿门。
- 对调试 mission/action 行为最有效。

缺点：

- 不是 Gazebo OAK-D 相机真实识别 world 中的 tag 纹理。
- 只能证明 3D 运动和行为控制链路，不证明仿真相机画质、视角、曝光、纹理识别。

推荐用途：

- 给客户 / 团队展示“机器人在 3D 场景中执行门流程”。
- 调试行为层参数：对齐速度、穿门距离、门类型、cmd_vel、odom。
- 在 Gazebo render sensor 问题修好前作为主线 demo。

### 3.2 Level 2：3D 场景 + ROS 视觉替身闭环

这是当前已经实现的 `door_apriltag_visual_demo.launch.py` 路线。

做法：

- Gazebo 负责 3D robot / world / physics。
- ROS camera publisher 负责稳定产生“相机看到门 tag”的图像。
- `apriltag_ros` 对该图像真实检测，发布 `/detections`。
- 行为层只消费 `/detections`，不关心图像来自 Gazebo 还是外部相机。

优点：

- 覆盖 perception-in-the-loop：图像 -> detector -> detections -> actions。
- 可重复、稳定、适合 CI 和演示。
- 不受 Gazebo Sensors / GPU driver 影响。

缺点：

- 相机图像不是 Gazebo 3D 渲染结果。
- 图像中的 tag 位置目前是 deterministic，不随机器人真实 3D 位姿变化。

推荐用途：

- 当前阶段最务实的主线。
- 做自动化回归：检测是否能从图像得到 `/detections`，门流程是否完成。

### 3.3 Level 3：完整 Gazebo 3D 视觉闭环

这是最终目标。

目标链路：

```text
Gazebo 3D world
  -> simulated OAK-D RGB camera
  -> Gazebo image topic
  -> ros_gz_bridge / ros_gz_image
  -> /oakd/rgb/preview/image_raw + /camera_info
  -> apriltag_ros
  -> /detections
  -> align_to_apriltag
  -> wait_for_tag_removed
  -> door_traverse
  -> robot physically crosses doorway in Gazebo
```

优点：

- 真实验证仿真相机视角、纹理、清晰度、机器人姿态与检测结果。
- 最接近实际机器人 perception stack。

缺点：

- 当前 `xiao-5080` 上被 Gazebo render sensor 崩溃阻塞。
- 需要同时处理 GPU/EGL/OGRE2、Gazebo sensor topics、ROS bridge、tag 可见性、门模型动态状态、Nav2/odom/TF 等多层问题。

推荐用途：

- 作为下一阶段专项，不建议直接压到当前 demo 主线。

## 4. 推荐路线

行业实践上，不建议把所有能力一次性耦合到同一个 demo。推荐分层推进：

```text
P0: 行为闭环稳定
P1: 3D 场景可视化稳定
P2: ROS 级视觉闭环稳定
P3: Gazebo camera sensor 单点稳定
P4: Gazebo camera -> ROS bridge -> apriltag_ros 稳定
P5: 动态门 / tag 可见性 / 穿门全闭环
```

当前项目已经完成：

- P0：行为闭环稳定。
- P1 的大部分：3D world 已存在；只需用非 `-s` 启动 Gazebo GUI。
- P2：ROS 级视觉闭环已完成。

下一步建议先做 P1 的 3D 展示版，再启动 P3/P4 的 Gazebo render sensor 专项。

## 5. 近期可执行方案

### 5.1 方案 A：立即获得 Gazebo 3D 场景展示

Terminal A 改为：

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
    custom_gz_args:="-r -v 2"
'
```

Terminal B 选择其一：

```bash
ros2 launch tourbot_bringup door_apriltag_demo.launch.py tag_id:=1
```

或：

```bash
ros2 launch tourbot_bringup door_apriltag_visual_demo.launch.py \
  tag_id:=1 \
  start_image_view:=true
```

注意：

- 不要同时运行两个 Terminal B，它们会启动同名 action server。
- 若 Gazebo GUI 不弹出，先检查 TurboVNC / DISPLAY / VirtualGL，而不是 AprilTag 代码。
- 这个方案展示的是 3D robot motion + 行为闭环，不是 Gazebo camera 感知闭环。

### 5.2 方案 B：拆分出 `world_3d_behavior.sdf`

为了避免 `world_no_sensors` 名称造成误解，可以新增一个语义更清楚的 world：

```text
src/tourbot_bringup/worlds/cardboard_city/world_3d_behavior.sdf
```

它与 `world_no_sensors.sdf` 内容相同，但文档定位为：

```text
3D scene + physics + robot motion + behavior demo, no render sensors
```

这样后续文档可以明确：

- `world_no_sensors.sdf`：技术 workaround 名称。
- `world_3d_behavior.sdf`：对外 demo 名称。
- `world.sdf`：full sensors research target。

### 5.3 方案 C：让门和 tag 在 3D world 中动态变化

当前 world 中门板和 tag 是静态视觉模型。为了让 Gazebo 3D 里也直观看到“门开了”，建议新增一个 lightweight door state controller。

实现方式：

- 新增 ROS node：订阅 `/door_demo/tag_visible` 或 `/door_open`。
- 通过 Gazebo Transport service 控制门板模型 / tag 模型：
  - 方式 1：set pose，把门板旋转或平移到打开位置。
  - 方式 2：set pose，把 tag 移到视野外。
  - 方式 3：删除/重生成 tag entity。
- Terminal B 开门时发布 `tag_visible=false`，3D 场景同步显示门打开。

推荐优先级：

1. 先用 set pose 移动 tag / 门板，最容易验证。
2. 再做带铰链的 revolute joint 和控制器。
3. 最后才做真实碰撞门扇、接触检测和避障规划。

这能让 3D 场景观感明显改善，即使还没有 Gazebo camera sensor，也能在 Gazebo GUI 中看到门状态变化。

## 6. Gazebo camera 闭环专项方案

完整 Gazebo camera 闭环建议单独建 feature 分支或实验目录，不要直接替换当前稳定 demo。

### 6.1 先做最小 sensor world

不要一开始就在 TurtleBot4 + full cardboard world 里调。

先做一个最小 world：

```text
world_camera_smoke.sdf
```

只包含：

- ground plane
- one fixed AprilTag plane
- one fixed RGB camera sensor
- `gz-sim-sensors-system`

验收：

- `gz sim -s --headless-rendering world_camera_smoke.sdf` 运行 60 秒不 139。
- `gz topic -l` 能看到 camera image topic。
- image topic 有帧率。

如果这里仍然 139，说明问题在 Gazebo render sensor / GPU stack，不在 TurtleBot4 或 AprilTag world。

### 6.2 固定 GPU / EGL / Gazebo 组合

当前 `xiao-5080` 是 RTX 5080，新硬件对容器内 EGL/OGRE2 组合更敏感。建议：

- 记录宿主机 NVIDIA driver 版本、container runtime 版本、Gazebo/gz-rendering/gz-sensors 版本。
- 固定 Docker image digest，不只用 tag。
- 对比两条路径：
  - NVIDIA EGL：`__EGL_VENDOR_LIBRARY_FILENAMES=/usr/share/glvnd/egl_vendor.d/10_nvidia.json`
  - CPU/software rendering：只在 Gazebo 支持的路径验证，不强行 `LIBGL_ALWAYS_SOFTWARE=1`。
- 分别测试 `ogre2`、`ogre`、`--headless-rendering`、GUI 模式。

验收：

- 最小 camera world 稳定。
- TurtleBot4 without AprilTag world 稳定。
- cardboard world without robot 稳定。
- cardboard world + robot + camera 稳定。

### 6.3 正确桥接 Gazebo image 到 ROS

桥接策略：

- 用 `ros_gz_bridge` 或 `ros_gz_image` 把 Gazebo image 转到 ROS `sensor_msgs/msg/Image`。
- 同步提供 `sensor_msgs/msg/CameraInfo`。
- 保持 image 和 camera_info 的 timestamp 一致，`apriltag_ros` 依赖这点做 pose estimation。
- topic 名称统一到现有 stack：

```text
/oakd/rgb/preview/image_raw
/oakd/rgb/preview/camera_info
/detections
```

不要让行为层感知数据源来自哪里。行为层只应该依赖 `/detections` 和 `/camera_info`。

### 6.4 AprilTag 纹理和相机参数验收

需要独立验证：

- tag 在相机画面中不镜像、不反转。
- tag 至少占据足够像素宽度，建议先让 tag 边长在图像中大于 80 px。
- 光照不过曝、不太暗。
- `apriltag_ros` family/size 与模型一致：

```text
family: 36h11
size: 0.162
```

验收命令：

```bash
ros2 topic hz /oakd/rgb/preview/image_raw
ros2 topic echo /detections --once
ros2 run image_view image_view --ros-args -r image:=/oakd/rgb/preview/image_raw
```

## 7. 动态门与真实穿门设计

完整 3D demo 不能只让 tag 消失，还要让门在 Gazebo 里打开，并且机器人实际穿过。

### 7.1 门模型分层

建议把门拆成三个 entity：

```text
door_frame_static
door_panel_dynamic
door_tag_mount
```

这样可以单独控制：

- 门框保持静态。
- 门板旋转或平移。
- tag 跟随门板，或开门后移出相机视野。

### 7.2 碰撞策略

分阶段引入 collision：

1. POC：门板无 collision，只演示视觉和动作。
2. SITL：门板 closed 时有 collision，open 后移除或旋转 collision。
3. 高保真：门板带 joint、limit、damping，机器人不能穿过 closed door。

不要一开始就做高保真碰撞门，否则调试会被控制、碰撞、导航、感知问题同时污染。

### 7.3 行为层接口

建议门状态统一成 topic/service：

```text
/door_demo/door_state
/door_demo/open_door
/door_demo/tag_visible
```

demo node 不应该直接操作 Gazebo world。它应该发布意图或状态，由 Gazebo door controller 执行 3D world 改变。

## 8. 推荐最终架构

最终架构建议如下：

```text
Gazebo world
  - TurtleBot4
  - cardboard_city geometry
  - dynamic door model
  - AprilTag visual models
  - OAK-D RGB camera sensor

ROS/Gazebo bridge
  - /clock
  - /cmd_vel
  - /odom
  - /tf
  - /oakd/rgb/preview/image_raw
  - /oakd/rgb/preview/camera_info

Perception
  - apriltag_ros
  - /detections

Behaviors
  - align_to_apriltag_server
  - wait_for_tag_removed_server
  - door_behavior_server

World state controller
  - door_open_controller
  - tag/door visual state sync

UI
  - Gazebo GUI for 3D scene
  - RViz2 for TF / robot / detections
  - image_view for camera image
```

关键原则：

- Gazebo 负责 3D physics/rendering。
- ROS bridge 只做 transport，不写业务逻辑。
- Perception 只消费 image/camera_info，发布 detections。
- Behavior 只消费 detections/odom，发布 cmd_vel。
- Door controller 只消费 door state，改变 Gazebo entity。
- Demo orchestration 只编排流程，不直接伪造多个层级的数据。

## 9. 验收标准

### 9.1 3D 行为展示版验收

- Gazebo GUI 能看到 `cardboard_city`、TurtleBot4、门板、AprilTag。
- Terminal B 触发后，机器人在 3D 中旋转对齐并向前穿门。
- `/cmd_vel`、`/odom`、`/tf` 正常。
- 不要求 Gazebo camera image。

### 9.2 ROS 视觉闭环版验收

- `image_view` 能看到门 / AprilTag / 检测框。
- `/oakd/rgb/preview/image_raw` 有帧率。
- `/detections` 初始含 `id=1`。
- 开门后 `/detections` 为空。
- 行为链路完整成功。

### 9.3 Gazebo camera 闭环版验收

- full sensors world 连续运行 10 分钟无 Gazebo 139。
- Gazebo camera image 能桥接到 ROS。
- `apriltag_ros` 从 Gazebo camera image 稳定发布 `/detections`。
- 门打开事件驱动 Gazebo 3D door/tag 状态变化。
- 机器人在 Gazebo 3D 中实际通过门口。
- 所有过程可通过 Gazebo GUI + RViz2 + image_view 同时观察。

## 10. 风险与决策

### 10.1 最大风险

最大风险不是 AprilTag 算法，而是当前 RTX 5080 + Docker + Gazebo Harmonic render sensors 的稳定性。

官方 Gazebo 文档也明确，使用需要 render engine 的 sensors 时，headless rendering 通常仍涉及 GPU / OGRE / EGL 路径。当前本机已验证该路径会崩溃，因此不应把主线 demo 绑定在这个风险点上。

### 10.2 推荐决策

短期：

- 用 `world_no_sensors.sdf` + 非 `-s` Gazebo GUI 做 3D 展示。
- 用 `door_apriltag_visual_demo.launch.py` 做 perception-in-the-loop 证明。
- 新增 door/tag Gazebo state controller，让 3D 场景中门能打开。

中期：

- 建最小 camera sensor world，解决 Gazebo render sensor 139。
- 打通 Gazebo camera -> ROS image -> apriltag_ros。

长期：

- 把 full sensors world 作为真实 SITL 场景。
- 引入动态门 collision / joint。
- 用 Nav2 + behavior tree 做更完整的“到门、识别、等待、穿门、继续 tour”。

## 11. 建议下一步任务拆分

1. 新增 `world_3d_behavior.sdf`，复制当前 no-sensors 3D world，作为对外 3D demo world。
2. 增加 `door_apriltag_3d_behavior_demo.launch.py`，组合：
   - Gazebo GUI custom world
   - 行为 demo
   - 可选 image_view
3. 新增 `door_state_gazebo_controller`，让 `/door_demo/tag_visible=false` 时移动门板/tag。
4. 新增 `world_camera_smoke.sdf`，只测 Gazebo render camera。
5. 解决 render sensor 139 后，再把 camera sensor 接回 TurtleBot4 / OAK-D topic。
6. 最后把 `mission.launch.py` 切到真实 Gazebo camera detections。

## 12. 参考资料

- Gazebo Sim headless rendering：<https://gazebosim.org/api/sim/9/headless_rendering.html>
- Gazebo Sensors library：<https://gazebosim.org/libs/sensors/>
- Gazebo Sim core capability：<https://gazebosim.org/libs/sim/>
- Gazebo ROS 2 integration / `ros_gz_bridge`：<https://gazebosim.org/docs/latest/ros2_integration/>
- `apriltag_ros` 本仓库说明：`src/apriltag_ros/README.md`

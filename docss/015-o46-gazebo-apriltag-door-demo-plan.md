# 015 · Gazebo camera 闭环崩溃根因定位与修复

> 日期：2026-07-01
> 主机：`xiao-5080`（RTX 5080 Blackwell, driver 580.126.20, Ubuntu 24.04.2, Docker 29.3.1 + nvidia runtime）
> 状态：**已修复并验证**

## 1. 结论先行

014 文档把崩溃原因猜测为「RTX 5080 Blackwell 新卡 + OGRE2/EGL 在容器环境下的兼容性问题」——**这个假设是错的**。

真正的根因是 **Gazebo Harmonic (Jazzy) 官方 apt 包在同一插件目录下同时打包了两个不兼容的 OGRE 渲染引擎插件**，导致进程内符号冲突 segfault。与 GPU 型号、驱动版本、EGL 路径完全无关——在任何 GPU 上跑这套容器都会崩。

修复方案已验证：**Dockerfile 加一行 `rm -f` 移除 OGRE1 插件文件**即可根治。

## 2. 根因深层解析

### 2.1 直接原因：OGRE1/OGRE2 插件 .so 共存导致符号冲突

容器内 `gz-rendering` 插件目录：

```
/opt/ros/jazzy/opt/gz_rendering_vendor/lib/gz-rendering-8/engine-plugins/
├── libgz-rendering8-ogre.so.8.2.3   ← OGRE1 插件，链接 libOgreMain.so.1.9.0
├── libgz-rendering8-ogre2.so.8.2.3  ← OGRE2 插件，链接 libOgreNextMain.so.2.3.3
└── （符号链接若干）
```

`RenderEngineManager` 启动时扫描该目录，同时发现两个插件并加载：

```text
[Wrn] [RenderEngineManager.cc:548] Found multiple render engine plugins in [gz-rendering-ogre]:
- gz::rendering::v8::OgreRenderEnginePlugin      ← OGRE1
- gz::rendering::v8::Ogre2RenderEnginePlugin     ← OGRE2/Next
Loading [gz::rendering::v8::OgreRenderEnginePlugin].
```

两套完全不同版本的 Ogre 库被 `dlopen` 到同一进程地址空间后，C++ 符号表里存在大量同名但内存布局不兼容的类型（`Ogre::Node`、`Ogre::Pass`、`Ogre::HlmsBlendblock` 等）。当渲染线程执行到 `Ogre2Node::AttachChild()` 时，动态链接器把调用解析到了 OGRE1 的 `Ogre::Node::getParent()`——该函数的 `this` 指针指向的是 OGRE2 对象布局，OGRE1 代码按自己的偏移去访问成员变量，直接 segfault。

### 2.2 间接原因：`ros-jazzy-gz-rendering-vendor` 官方包把 OGRE1 当依赖

```bash
$ apt-cache rdepends libogre-1.9.0t64
Reverse Depends:
  ros-jazzy-gz-rendering-vendor   ← 官方包本身拉入 OGRE1
  libogre-1.9-dev
```

这不是用户环境配置错误或 Dockerfile 引入的杂包——是官方发行包自身的依赖设计缺陷（为了 Gazebo Classic 向后兼容同时打包了 OGRE1 插件）。

### 2.3 二级问题：world.sdf 和 robot model 重复声明 sensors-system

当 `world.sdf` 和 TurtleBot4 robot model 各自声明一个 `gz-sim-sensors-system` 插件时，会在同一 gz-sim 进程内创建两个 Sensors 渲染实例。第二个实例尝试创建第二个 OGRE 渲染场景时，因为第一个已经占用了全局状态，导致 null pointer segfault。

TurtleBot4 官方 worlds（warehouse, depot, maze）的做法是：**注释掉 world 级的 sensors-system**，让 robot model 自带的唯一 sensors-system 生效。

本项目的 `world_no_sensors.sdf` 正好删除了 world 级 sensors-system，因此是正确的选择。

### 2.4 TurtleBot4 robot model 配置 `render_engine=ogre`

```xml
<!-- turtlebot4.urdf.xacro 渲染出的 URDF 中 -->
<plugin filename="libgz-sim-sensors-system.so" name="gz::sim::systems::Sensors">
  <render_engine>ogre</render_engine>
</plugin>
```

Robot 自带的 sensors-system 指定了 `ogre`（OGRE1）。移走 OGRE1 插件后，Gazebo 会自动 graceful fallback：

```text
[Err] Engine [ogre] is not supported. Loading OGRE2 instead.
```

这个 fallback 完全正常工作，不需要修改 TurtleBot4 的 URDF。

## 3. 为什么与 RTX 5080/Blackwell 无关

| 证据 | 说明 |
|------|------|
| `nvidia-smi` 正常 | RTX 5080 + driver 580.126.20 在容器内工作正常 |
| `glxinfo -B` 正常 | OpenGL 4.6 完整支持，NVIDIA 580.126.20 |
| 容器内 NVIDIA 库版本一致 | `libGLX_nvidia.so.580.126.20` 与宿主机匹配 |
| minimal camera world 不崩溃 | 没有 TurtleBot4 spawn 的纯 camera world 跑 40 秒正常 |
| world.sdf 单独加载不崩溃 | cardboard_city world（含所有模型）单独跑 40 秒正常 |
| `libEGL warning` 是噪音 | 不崩溃和崩溃的场景都打印同样的 libEGL warning |

崩溃仅在 TurtleBot4 spawn 后出现——因为 spawn 触发了渲染线程调用 `CreateModel` / `AttachChild`，这才走进了两套 Ogre 符号冲突的代码路径。

## 4. 为什么 codex 没能解决

1. **被 `libEGL warning` 日志误导**：容器内 EGL/DRI 探测的正常警告噪音在任何场景都会打印，但 codex 可能把这些当成崩溃的直接原因，陷入 GPU/驱动/EGL 排障死胡同。
2. **没做最小可复现隔离**：只有在 TurtleBot4 spawn 后才崩溃，minimal world 和 world-only 都不崩，需要精确的对照实验才能定位范围。
3. **RTX 5080 是新卡，先入为主怀疑硬件**：Blackwell 架构确实有很多真实的生态适配问题（PyTorch、Isaac Sim 等），容易让人优先往硬件方向想。
4. **根因线索隐藏在 `-v 4` 详细日志中间**：`RenderEngineManager` 的"Found multiple render engine plugins"警告是最直接的线索，但它被大量 INFO/DEBUG 日志淹没，低日志级别（`-v 2`）下不可见。

## 5. 已验证的修复方案

### 5.1 Dockerfile 修复（已实施）

在 `docker_stuff/Dockerfile.jazzy` 中，apt 安装完成后加一行：

```dockerfile
# Workaround: remove OGRE1 render engine plugin to prevent symbol clash with
# OgreNext 2.3 (OGRE2).  Both plugins coexist in the same directory and
# RenderEngineManager loads both into the same process, causing Ogre::Node
# symbols from libOgreMain.so.1.9.0 to collide with OgreNext equivalents
# and segfault in gz-sim-sensors-system RenderThread.
RUN rm -f /opt/ros/jazzy/opt/gz_rendering_vendor/lib/gz-rendering-8/engine-plugins/libgz-rendering*-ogre.so* \
    && rm -f /opt/ros/jazzy/opt/gz_rendering_vendor/lib/gz-rendering-8/engine-plugins/libgz-rendering8-ogre.so*
```

**特点：**
- 不通过 `apt remove`（避免级联删除整个 gz-sim 仿真栈），只做文件级删除
- 不影响 apt 包管理状态，后续 `apt upgrade` 可能会恢复文件（但重建容器时 Dockerfile 会再次删除）
- `libogre-1.9.0t64` 包本身仍然安装在系统里，不影响任何其他可能依赖它的工具

### 5.2 World 选择（已有）

使用 `world_no_sensors.sdf`（不含 `gz-sim-sensors-system` 声明），让 TurtleBot4 robot model 自带的唯一 sensors-system 生效。这与 TurtleBot4 官方 worlds 的做法一致。

### 5.3 运行时行为

修复后的日志序列：

```text
[Err] Failed to load plugin [gz-rendering-ogre] : couldn't find shared library.
[Err] Engine [ogre] is not supported. Loading OGRE2 instead.
[Msg] Loading plugin [gz-rendering-ogre2]
[Dbg] Rendering Thread initialized
[Dbg] RGB images for [...] advertised on [...]
[Dbg] Depth images for [...] advertised on [...]
[Dbg] Points for [...] advertised on [...]
[Dbg] Camera info for [...] advertised on [...]
```

虽然有两行 `[Err]`，但这是**正常的 graceful fallback**——robot model 配置的 `render_engine=ogre` 找不到 OGRE1 插件，自动切换到 OGRE2，渲染完全正常工作。

## 6. 验证实验记录

### 6.1 对照实验 1：原始环境 + TurtleBot4 spawn → segfault

```bash
ros2 launch tourbot_bringup sim.launch.py use_custom_sim:=true \
  start_navigation:=false custom_gz_args:="-r -s -v 4" \
  custom_world:=.../world
```

结果：~2 秒后 segfault，堆栈：`Ogre2Node::AttachChild` → `libOgreMain.so.1.9.0::Ogre::Node::getParent()`

### 6.2 对照实验 2：移走 OGRE1 插件 + world.sdf（有 sensors-system）→ null ptr crash

world.sdf 和 robot model 各有一个 sensors-system，第二个创建渲染场景时 null pointer。

### 6.3 对照实验 3：移走 OGRE1 插件 + world_no_sensors.sdf → ✅ 成功

```bash
# 移走 OGRE1 插件后
ros2 launch tourbot_bringup sim.launch.py use_custom_sim:=true \
  start_navigation:=false custom_gz_args:="-r -s --headless-rendering -v 4" \
  custom_world:=.../world_no_sensors
```

结果：运行 60 秒不崩溃，OAK-D camera topics 全部正常 advertise，entity 创建成功。

### 6.4 方案 A 验证：替换 Gazebo/DarkGrey 材质 → 无效

实验证明崩溃发生在 `CreateModel` / `AttachChild` 通用路径，与材质定义无关。`Gazebo/DarkGrey` warning 只是伴生现象，不是因果关系。

### 6.5 方案 B 验证：apt remove libogre-1.9.0t64 → 不可行

dry-run 显示会级联删除 21 个包（包括 gz-sim-vendor、turtlebot4-simulator、nav2-bringup 等整个仿真栈）。

## 7. 被排除的错误假设

| 假设 | 排除证据 |
|------|----------|
| RTX 5080 Blackwell 不兼容 OGRE2 | minimal camera world 在同一 GPU 上完美运行 |
| NVIDIA driver 580.126.20 有 bug | glxinfo/nvidia-smi 正常，驱动功能完整 |
| 容器内 NVIDIA userspace 库版本不匹配 | 确认 580.126.20 与宿主机一致 |
| EGL 路径配置错误 | libEGL warning 在不崩溃场景也出现 |
| `Gazebo/DarkGrey` 材质触发崩溃 | 替换所有材质后仍崩，证明无因果关系 |
| `--headless-rendering` 有问题 | 有无 headless 都崩（因为根因是符号冲突不是渲染模式）|

## 8. 修复后解锁的能力

修复后，014 文档规划的 **Level 3 完整 Gazebo 3D 视觉闭环**不再被阻塞，且已在 012 文档继续实现：

```text
Gazebo world + TurtleBot4 OAK-D rgbd_camera
  → gz topic (RGB image / depth / points / camera_info)
  → ros_gz_bridge
  → /oakd/rgb/preview/image_raw + /camera_info
  → apriltag_ros
  → /detections
  → 行为层
```

当前实现入口：

```text
src/tourbot_bringup/launch/door_apriltag_gazebo_world_demo.launch.py
src/tourbot_bringup/launch/door_apriltag_gazebo_demo.launch.py
```

关键补齐：

- Gazebo OAK-D image/camera_info 已 bridge 到 `/oakd/rgb/preview/image_raw` 与 `/oakd/rgb/preview/camera_info`。
- `apriltag_ros` 已使用 Gazebo 专用参数从真实渲染图像检测 `tag_id=1`。
- `door_state_gazebo_controller` 已通过 `/world/world_demo/set_pose` 控制 tag/门板开闭状态。
- `door_behavior_server` 已通过 `/diffdrive_controller/cmd_vel` + `/odom` 完成真实仿真穿门。

## 9. 下一步

1. ✅ Dockerfile 修复已实施，下次 `docker compose build` 自动生效
2. ✅ bridge 配置已验证：Gazebo camera topic 可桥接到 `/oakd/rgb/preview/image_raw`
3. ✅ `apriltag_ros` 已能从 Gazebo 渲染图像中检测到 AprilTag
4. ✅ 行为层已接入，Level 3 全闭环已完成
5. ✅ `world_no_sensors.sdf` 的门 demo 已回归通过
6. 后续优化：把 tag/门板的 Gazebo 状态规格从 Python 常量迁移到 YAML 配置，便于扩展更多门

## 10. 参考

- 014 文档：`docss/014-gazebo-apriltag-door-demo-plan.md`（本文档修正其根因假设）
- Dockerfile 改动：`docker_stuff/Dockerfile.jazzy`
- 崩溃插件路径：`/opt/ros/jazzy/opt/gz_rendering_vendor/lib/gz-rendering-8/engine-plugins/`
- Gazebo Sim 版本：8.11.0
- gz-rendering-vendor 版本：0.0.7-1noble.20260226.001618
- TurtleBot4 Simulator 版本：2.0.2-1noble.20260616.091643

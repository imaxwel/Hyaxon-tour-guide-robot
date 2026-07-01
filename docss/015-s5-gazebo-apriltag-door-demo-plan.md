# 015 · Gazebo AprilTag door demo：camera 闭环崩溃根因复核与方案

> 日期：2026-07-01
> 主机：`xiao-5080`（RTX 5080, driver 580.126.20, Ubuntu 24.04.2, Docker 29.3.1 + nvidia runtime）
> 背景：014 号文档把当前 Gazebo camera 闭环受阻的原因归因为「RTX 5080 容器环境下 OGRE2/EGL 崩溃」。本文档用第一手复现实验重新定位根因，结论与 014 的初始猜测**不同**：崩溃与 GPU 型号、驱动版本、EGL 均无关，是 Gazebo Harmonic (Jazzy) 官方 apt 包自身携带的 OGRE1/OGRE2 渲染插件共存冲突。

## 1. 结论先行

**014 文档的猜测（RTX 5080 Blackwell + OGRE2/EGL 兼容性问题）是错误的根因假设**，实际根因是：

- 系统里同时装了两套完全不同的渲染引擎库：
  - `libogre-1.9.0t64`（Ubuntu 24.04 系统包，OGRE Classic 1.9，供 Gazebo Classic 兼容用）
  - `libOgreNextMain.so.2.3.3`（`ros-jazzy-gz-ogre-next-vendor`，Gazebo Harmonic 实际用的 OGRE-Next 2.3）
- 关键：**`libogre-1.9.0t64` 是被 `ros-jazzy-gz-rendering-vendor` 官方包直接反向依赖装进来的**，不是环境配置错误或用户手动装的杂包。
- `gz-rendering` 的 `RenderEngineManager` 在加载 render engine plugin 时扫描到同名 `[gz-rendering-ogre]` 插件命名空间下存在两个不同版本的插件实现（`OgreRenderEnginePlugin` 与 `Ogre2RenderEnginePlugin`），日志会打印明确警告：

```text
[Wrn] [RenderEngineManager.cc:548] Found multiple render engine plugins in [gz-rendering-ogre]:
- gz::rendering::v8::OgreRenderEnginePlugin
- gz::rendering::v8::Ogre2RenderEnginePlugin
Loading [gz::rendering::v8::OgreRenderEnginePlugin].
```

- 当 world 中的模型使用了 Gazebo 不原生支持、需要走内部 fallback 解析的 Ogre material script（本项目 cardboard_city world 里的门板、纸箱等模型正是如此，日志显示 `Using an internal gazebo.material to parse Gazebo/DarkGrey`），Sensors 系统的渲染线程会调用 OGRE2 材质管线 `Ogre2Material::SetAlphaFromTexture` → `Ogre::HlmsBlendblock::setBlendType`。由于进程里同时加载了 OGRE1 (`libOgreMain.so.1.9.0`) 和 OgreNext 2.3 (`libOgreNextMain.so.2.3.3`) 两套同名 C++ 符号/类型（`Ogre::Pass`、`Ogre::HlmsBlendblock` 等在两个版本里的内存布局完全不同），动态链接器解析到了错误的符号实现，最终在 `Ogre::Pass::_getBlendFlags` 里访问了不属于该对象的内存，触发 segfault（exit code 139）。

- 这个崩溃**与 RTX 5080、Blackwell 架构、580.126.20 驱动、EGL 均无关**。只要容器里同时存在这两套 Ogre 库，且渲染路径触发了这条材质代码，任何 GPU（包括 CPU 软件渲染）上都会崩。GPU 型号只是「恰好这台机器是 RTX 5080」，不是崩溃的因果条件。

## 2. 为什么 codex 没能解决

结合已知信息推断（非直接观测 codex 的会话记录，仅基于问题现象和常见排障路径），codex 之前的方向出现偏差的可能原因：

1. **被表面证据误导**：日志里确实有大量 `libEGL warning`（`pci id for fd ...`、`egl: failed to create dri2 screen`），这些是容器内 X11/VirtualGL 转发场景下的正常警告噪音（本次复现里，即使程序最终正常运行 40 秒不崩溃的 smoke test，也会打印同样的 libEGL warning）。如果排障时把这些警告当成崩溃的直接原因，就会一头扎进 EGL/驱动/GPU 兼容性这个死胡同。
2. **没有做「最小可复现」隔离**：014 文档里 6.1 节其实已经规划了"先做最小 sensor world"的正确思路，但如果没有真正执行这一步、或者最小 world 恰好没有触发 Ogre material script 解析路径（本次复现验证：不含自定义材质的最小 camera world 完全不崩溃），就无法把问题范围从"GPU/驱动"收窄到"特定 material 解析路径"。
3. **没有读 `RenderEngineManager` 的插件加载警告**：这条警告在 `-v 4` 详细日志里明确写了"发现多个同名渲染引擎插件"，是最直接的根因线索，但它出现在大量 INFO/DEBUG 日志中间，容易被忽略，尤其是如果只在 `-v 2` 或更低日志级别下调试就根本看不到。
4. **RTX 5080 是新卡，容易先入为主怀疑硬件**：Blackwell 架构确实有不少真实的软件生态适配问题（PyTorch/CUDA kernel、Isaac Sim 等在网上有大量已知 issue），这会让人倾向于优先怀疑"新卡不兼容"，而不是去怀疑"官方 apt 包本身有依赖冲突"这种更反直觉的可能性。

## 3. 复现实验记录（本次新增的第一手证据）

在 `xiao-5080` 上通过 `docker compose -f docker_stuff/compose.yaml run --rm --no-deps dev` 进入项目容器，做了以下对照实验：

### 3.1 最小 camera-only world（不含自定义材质）

```bash
gz sim -s -r --headless-rendering -v 4 /tmp/smoke.sdf
```

world 只有 ground plane + 一个固定 camera + `gz-sim-sensors-system`。**结果：运行 20 秒、40 秒均不崩溃**，`Rendering Thread initialized` 正常输出，camera topic 正常 advertise，收到 SIGTERM 后正常退出（exit 0）。

### 3.2 cardboard_city/world.sdf，server-only，无 TurtleBot4 spawn

```bash
gz sim -s -r --headless-rendering -v 4 /ws/src/tourbot_bringup/worlds/cardboard_city/world.sdf
```

**结果：运行 40 秒不崩溃**，正常退出。说明门板/纸箱/AprilTag 模型本身被加载到 world 里并不会立刻崩溃——直到有渲染线程真正对这些模型的材质做完整处理。

### 3.3 完整 `sim.launch.py`（真实项目路径），带 TurtleBot4 spawn

```bash
ros2 launch tourbot_bringup sim.launch.py \
  use_custom_sim:=true start_navigation:=false \
  custom_gz_args:="-r -s -v 4" \
  custom_world:=/ws/src/tourbot_bringup/worlds/cardboard_city/world
```

**结果：约 2 秒后触发 segfault，exit code 139**，完整堆栈：

```text
[Wrn] [RenderEngineManager.cc:548] Found multiple render engine plugins in [gz-rendering-ogre]:
- gz::rendering::v8::OgreRenderEnginePlugin
- gz::rendering::v8::Ogre2RenderEnginePlugin
Loading [gz::rendering::v8::OgreRenderEnginePlugin].

Stack trace (most recent call last) in thread 965:
#7  libgz-sim-sensors-system.so, gz::sim::v8::systems::SensorsPrivate::RenderThread()
#6  libgz-sim-sensors-system.so, gz::sim::v8::systems::SensorsPrivate::RunOnce()
#5  libgz-sim8-rendering.so.8, gz::sim::v8::RenderUtil::Update()
#4  libgz-sim8-rendering.so.8, gz::sim::v8::SceneManager::CreateVisual(...)
#3  libgz-sim8-rendering.so.8, gz::sim::v8::SceneManager::LoadMaterial(sdf::v14::Material const&)
#2  libgz-rendering-ogre2.so, gz::rendering::v8::Ogre2Material::SetAlphaFromTexture(...)
#1  libOgreNextMain.so.2.3.3, Ogre::HlmsBlendblock::setBlendType(Ogre::SceneBlendType)
#0  libOgreMain.so.1.9.0, Ogre::Pass::_getBlendFlags(...)   <-- 跳进了错误的 OGRE1 符号
Segmentation fault (core dumped)
```

注意 `#1` 还在 `libOgreNextMain.so.2.3.3`（正确的 OGRE2/Next 库），`#0` 却已经落入 `libOgreMain.so.1.9.0`（OGRE1 库）——这是符号解析错乱的直接证据。

### 3.4 依赖链确认

```bash
apt-cache rdepends libogre-1.9.0t64
# Reverse Depends:
#   ros-jazzy-gz-rendering-vendor
#   libogre-1.9-dev
```

`libogre-1.9.0t64` 是被 `ros-jazzy-gz-rendering-vendor`（Gazebo Harmonic 官方 vendor 包）**直接反向依赖**装进来的，说明这是官方发行包自带的组合，不是项目 Dockerfile 或用户操作引入的额外冲突。

### 3.5 排除 GPU/驱动/EGL 因素

- `nvidia-smi`、`glxinfo -B`（经 VirtualGL）均正常返回 RTX 5080 + driver 580.126.20 + OpenGL 4.6 完整支持。
- 容器内 NVIDIA userspace 库版本（`libGLX_nvidia.so.580.126.20`、`libEGL_nvidia.so.580.126.20`）与宿主机驱动版本完全一致，非旧版本残留。
- `libEGL warning: egl: failed to create dri2 screen` 在崩溃场景和不崩溃场景中都会出现，是 mesa EGL 在探测非 NVIDIA fallback 设备节点时的正常噪音，不是崩溃的先兆。

## 4. 为什么这比"怀疑 Blackwell/EGL 兼容性"是更好的方案

1. **根因层级不同**：Blackwell/EGL 假设需要等 NVIDIA 或 Gazebo 上游修复驱动/渲染栈，时间不可控，且本次验证已经证明该假设站不住脚——同一驱动、同一 GPU，minimal world 完全不崩溃。继续在这个方向排查是在往错误的方向消耗时间。
2. **真实根因是可在当前环境内直接修复的软件包问题**，不需要等待任何外部厂商修复，也不需要更换硬件或降级驱动。
3. **修复路径明确、风险低、可验证**：见下节方案，均可在现有容器内直接验证，不引入新的技术栈。

## 5. 修复方案（按风险从低到高排列）

### 5.1 方案 A（推荐首选）：让 world 里的模型避免触发内部 Ogre material script fallback 解析

现象里明确写着：

```text
[Wrn] [SdfEntityCreator.cc:933] Gazebo does not support Ogre material scripts.
[Wrn] [SdfEntityCreator.cc:949] Using an internal gazebo.material to parse Gazebo/DarkGrey
```

`cardboard_city` world 里的门板/纸箱模型用了 `Gazebo/DarkGrey` 这种 Gazebo Classic 风格的材质名（Ogre1 material script 语法），Gazebo Harmonic 只是靠内部 fallback 表勉强兼容，而这条 fallback 解析路径正是触发崩溃堆栈的入口（`SceneManager::LoadMaterial` → `Ogre2Material::SetAlphaFromTexture`）。

做法：把这些模型的 `<material>` 定义改为 SDF 原生的 `<ambient>/<diffuse>/<specular>` 颜色值，或使用 PBR `<metal>` / `<pbr>` 材质定义，不再依赖 `Gazebo/DarkGrey` 这种 script 名称。

```xml
<!-- 替换前 -->
<material>
  <script>
    <name>Gazebo/DarkGrey</name>
  </script>
</material>

<!-- 替换后 -->
<material>
  <ambient>0.2 0.2 0.2 1</ambient>
  <diffuse>0.3 0.3 0.3 1</diffuse>
  <specular>0.1 0.1 0.1 1</specular>
</material>
```

验收：修改后重跑 3.3 节的完整 launch 命令，确认不再进入 `LoadMaterial` → segfault 路径。

风险：低，只改 SDF 材质定义，不影响物理/碰撞/拓扑。

### 5.2 方案 B：卸载/隔离冲突的 OGRE1 库（容器级 workaround）

如果一时找不全所有触发 fallback 的模型，可以在 Dockerfile 里强制移除或屏蔽 `libogre-1.9.0t64` 对 `gz-rendering` 运行时的可见性：

```dockerfile
# 在 apt 安装 gz 相关包之后，显式移除仅用于 Gazebo Classic 兼容的 OGRE1 运行库
# 注意：这会移除 libogre-1.9-dev，如果后续有其他包依赖它需要重新评估
RUN apt-get remove -y --purge libogre-1.9-dev libogre-1.9.0t64 || true
```

或者更保守地，通过 `LD_LIBRARY_PATH` 顺序 / plugin 目录隔离，避免 `RenderEngineManager` 同时扫描到两个插件。需要先确认 `libogre-1.9.0t64` 是否被 `rviz_ogre_vendor` 或其他必需组件间接依赖（本次检查 `rviz_ogre_vendor` 用的是自带的 `libOgreMain.so.1.12.10`，独立于系统 `libogre-1.9`，理论上移除系统包不影响 RViz）。

验收：移除后确认 `ros2 launch ... rviz2` 等仍能正常渲染，再重跑 3.3 节命令确认不崩溃。

风险：中，需要验证移除后没有破坏其他依赖 OGRE1 的功能（如 Gazebo Classic 相关工具，本项目目前不使用 Gazebo Classic，风险可控）。

### 5.3 方案 C：升级 Gazebo/ROS 发行版，等待上游修复插件命名冲突

这是一个已知会在 `RenderEngineManager` 里出现歧义的插件命名问题，理论上上游后续版本可能会修正插件目录结构或加 explicit engine 选择逻辑。但这依赖 Gazebo Ionic/Jetty 等新版本发布和验证，时间不可控，不建议作为当前主线依赖。

可以作为长期观察项，但**不需要**因为等待上游修复而阻塞当前 demo。

## 6. 修正后的推荐路线

在 5.1（首选）验证通过之前，仍建议维持 014 文档里 P0～P2 的分层路线（行为闭环 → 3D 可视化 → ROS 视觉替身闭环）作为主线不动，因为这部分和本次修复是正交的，不冲突。

修正点仅在于：

- **不要再把"Gazebo camera 闭环受阻"归因为 RTX 5080/Blackwell/EGL 硬件兼容性问题**，这会让排障方向持续跑偏，也会让团队产生"要等 NVIDIA/Gazebo 上游修复才能推进"的错误预期。
- P3（Gazebo camera sensor 单点稳定）的验收标准应更新为：先定位并替换 world 中所有触发 `Ogre material scripts` fallback 解析的材质定义（5.1），而不是去对比不同 render engine / headless 参数组合。
- 014 文档 6.2 节里"固定 GPU/EGL/Gazebo 组合"的排查方向可以降级为次要观察项，不再是 P3 的主要工作量。

### 6.1 下一步任务（替换 014 文档第 11 节里 P3/P4 相关任务）

1. 扫描 `src/tourbot_bringup/worlds/cardboard_city/` 下所有 `.sdf`/`model.sdf` 文件里的 `<script><name>Gazebo/...</name></script>` 材质引用，逐个替换为原生 `<ambient>/<diffuse>/<specular>` 或 PBR 材质。
2. 重跑 3.3 节命令，确认完整 `sim.launch.py`（含 TurtleBot4 spawn + 全部 world 模型）在 `-r`（GUI）和 `-r -s`（headless）两种模式下均能稳定运行 10 分钟不崩溃。
3. 确认不崩溃后，按 014 文档 6.3/6.4 节把 Gazebo camera image 通过 `ros_gz_bridge` 接到 `/oakd/rgb/preview/image_raw`，跑通 `apriltag_ros` 真实检测。
4. 如果替换所有材质后仍有个别场景崩溃，再执行 5.2 节的容器级隔离方案作为兜底。
5. 把这次排障过程和结论同步给 codex 此前的排障记录，避免后续维护者再次走回"怀疑 RTX 5080 硬件兼容性"的方向。

## 7. 参考资料

- 本次复现所用命令与堆栈：见第 3 节（一次性验证，未发起外部 issue）。
- Gazebo Sensors library：<https://gazebosim.org/libs/sensors/>
- Gazebo headless rendering：<https://gazebosim.org/api/sim/9/headless_rendering.html>
- 014 号文档：`docss/014-gazebo-apriltag-door-demo-plan.md`（本文档修正其根因假设，其余分层方案与验收标准保持有效）

# Gazebo 空世界与 controller_manager 超时排查结论

更新时间：2026-06-30

## 1. 当前结论

这次问题的表面现象是：

- Gazebo GUI 打开后，看起来物理世界空无一物。
- launch 日志里反复出现 `controller_manager` spawner 超时：

```text
Failed getting a result from calling /controller_manager/switch_controller
Failed getting a result from calling /controller_manager/list_controllers
RuntimeError: Could not successfully call service /controller_manager/...
```

排查后的结论是：

- 这不是单纯的 X11 权限问题，`xhost +local:` 只能解决一部分 GUI 连接权限，不能保证 Gazebo server、渲染引擎、Sensors system 和 `ros2_control` 都稳定启动。
- `controller_manager` 超时是下游症状。TurtleBot4/Create3 的 `controller_manager` 来自 Gazebo 仿真里的 `ros2_control` 链路；当 Gazebo server、传感器渲染或仿真更新线程卡住时，spawner 就会等不到 `/controller_manager/list_controllers` 或 `/controller_manager/switch_controller` 的有效响应。
- GUI 里看起来“空世界”也不能直接等同于 world 没加载。需要用 Gazebo transport 查询 server 端 scene，确认模型是否真的存在。
- 当前工程已经按更稳妥的方式调整为：Gazebo server 和 GUI 分离启动、默认使用项目自定义 `cardboard_city` world、使用 `ogre` 渲染、移除 world 级 Sensors plugin、延迟并顺序加载控制器。

一句话判断：

> 原问题的根因在 Gazebo 仿真服务端和渲染/传感器初始化链路不稳定，导致 `ros2_control` controller manager 不能及时处理服务请求；spawner timeout 是结果，不是首要根因。

## 2. 当前推荐启动流程

在 `dellnb` 宿主机上：

```bash
cd ~/4sim/gh-ref/tour-guide-robot/Hyaxon-tour-guide-robot
./docker_stuff/setup-host.bash
docker compose --env-file docker_stuff/.env -f docker_stuff/compose.sim.yaml up -d sim
docker compose --env-file docker_stuff/.env -f docker_stuff/compose.sim.yaml exec sim bash
```

不推荐把下面命令作为日常默认做法：

```bash
xhost +local:
```

它会放宽本机所有 local client 的 X11 访问权限。常规流程优先使用 `setup-host.bash` 生成的 `docker_stuff/.xauth`。如果 GUI 仍然打不开，再临时使用更收敛的：

```bash
xhost +SI:localuser:"$(id -un)"
```

容器内：

```bash
cd /workspace
source /opt/ros/jazzy/setup.bash
rosdep update --rosdistro jazzy
rosdep install --from-paths src --ignore-src -r -y --rosdistro jazzy -t buildtool -t build -t exec
colcon build --packages-select tourbot_bringup --symlink-install
source install/setup.bash
ros2 launch tourbot_bringup sim.launch.py
```

当前默认启动的是轻量项目仿真：

- `use_custom_sim:=true`
- `custom_world` 指向 `tourbot_bringup/worlds/cardboard_city/world.sdf`
- SDF world name 是 `cardboard_city`
- `rviz:=false`
- `localization:=false`
- `nav2:=false`
- `gazebo_gui:=true`

如果只想验证 Gazebo server 和控制器，不打开 GUI：

```bash
ros2 launch tourbot_bringup sim.launch.py gazebo_gui:=false
```

如果需要完整导航，再显式打开：

```bash
ros2 launch tourbot_bringup sim.launch.py localization:=true nav2:=true rviz:=true
```

## 3. 已采用的修复点

### 3.1 Gazebo server 和 GUI 分离

当前自定义仿真不再把 server 和 GUI 强绑在同一个 Gazebo 启动路径里。

server 侧使用类似参数：

```text
world.sdf -r -s -v 4 --headless-rendering --render-engine-server ogre
```

GUI 侧单独延迟启动：

```text
-g -v 4 --render-engine-gui ogre --gui-config ...
```

这样做的目的：

- server 端先负责加载 world、spawn robot、运行 physics 和控制器。
- GUI 端只是 client，GUI 渲染出问题时不应该直接拖垮 server 端验证。
- 可以用 `gazebo_gui:=false` 做 headless smoke test，先确认仿真后端是活的。

### 3.2 移除 world 级 Sensors system

`cardboard_city/world.sdf` 当前保留了基础系统插件：

- `gz-sim-physics-system`
- `gz-sim-user-commands-system`
- `gz-sim-scene-broadcaster-system`
- `gz-sim-contact-system`
- `gz-sim-imu-system`

不再在 world 顶层额外加载 `gz-sim-sensors-system`。

原因是 TurtleBot4/Create3 模型、相机、雷达和 Gazebo bridge 本身已经有传感器相关集成。world 顶层再抢先加载 Sensors/render context，容易在容器、X11 和 OGRE2 组合下引发重复初始化或退出时崩溃。日志里这类行本身不一定是错误：

```text
[Sensors.cc:953] Initialization needed
[Sensors.cc:349] Initializing render context
```

但如果随后 controller spawner 长时间等不到响应，就要把它当作 Gazebo server/render/sensor 链路没有稳定完成的信号，而不是只盯着 spawner 本身。

### 3.3 使用更保守的渲染路径

当前 Docker Compose 默认偏向软件渲染和 Mesa：

```text
LIBGL_ALWAYS_SOFTWARE=1
MESA_LOADER_DRIVER_OVERRIDE=llvmpipe
QT_X11_NO_MITSHM=1
```

Gazebo 自定义启动也显式使用 `ogre`，而不是默认依赖更挑环境的 `ogre2`。

这不是为了追求最高帧率，而是先保证在笔记本 + Docker + X11 的组合里稳定复现和调试。等 server、控制器、Nav2 都稳定后，再考虑切回硬件渲染或 NVIDIA/Intel GPU 加速。

### 3.4 不覆盖系统 Gazebo 路径

launch 里使用追加方式设置 Gazebo 资源和 GUI 插件路径：

- `GZ_SIM_RESOURCE_PATH`
- `GZ_GUI_PLUGIN_PATH`

原则是把项目 world、TurtleBot4 world、Create3 world 和 ROS share 路径追加进去，而不是把系统默认路径覆盖掉。否则 Gazebo 可能找不到官方模型、GUI plugin 或系统 plugin，表现出来就可能是空 scene、spawn 失败或 GUI 面板异常。

### 3.5 控制器延迟并顺序加载

当前项目自定义 spawn 流程会先 spawn robot 和 dock，再延迟加载控制器：

- `controller_start_delay` 默认 `10.0`
- `robot_nodes_start_delay` 默认 `18.0`
- `controller_manager_timeout` 默认 `90`
- `controller_service_call_timeout` 默认 `45`
- `controller_switch_timeout` 默认 `45`

控制器加载顺序是：

1. `joint_state_broadcaster`
2. `diffdrive_controller`

`diffdrive_controller` 会在 `joint_state_broadcaster` spawner 退出后再启动。这样能减少 Gazebo 刚 spawn 完 robot 时，多个 controller 同时抢服务请求造成的竞态。

注意：这些 timeout 只是容错边界。真正的修复不是无限增大 timeout，而是先让 Gazebo server、world、robot 和 `ros2_control` 插件稳定进入 update loop。

### 3.6 world 与 map 对齐

当前默认 world 文件是：

```text
src/tourbot_bringup/worlds/cardboard_city/world.sdf
```

其中包含：

- `ground_plane`
- 从 `map_area.pgm` 生成的 `map_walls`
- 113 个墙体 box link
- 光源、scene、GUI 配置和 1ms physics 设置

这能避免 RViz 里看到 2D map 障碍，但 Gazebo 3D world 没有对应 collision/visual 的问题。

## 4. 如何判断 world 不是空的

不要只看 Gazebo GUI。另开一个容器 shell，执行：

```bash
cd /workspace
source /opt/ros/jazzy/setup.bash
source install/setup.bash

gz service -s /world/cardboard_city/scene/info \
  --reqtype gz.msgs.Empty \
  --reptype gz.msgs.Scene \
  --timeout 5000 \
  --req '{}'
```

正常情况下，返回内容里应该能看到类似模型名：

```text
ground_plane
map_walls
standard_dock
turtlebot4
```

如果这里能看到模型，但 GUI 画面看起来空，优先排查：

- GUI camera 是否看向了正确位置。
- GUI client 是否连接到了同一个 Gazebo partition/world。
- GUI render engine 是否初始化失败。
- 容器内 OpenGL/Mesa 是否异常。

如果这里也没有模型，才说明 server 端 world 或 spawn 本身失败，需要回头看 `gz sim -s` 日志、resource path、world path 和 spawn 命令。

## 5. 如何判断 controller_manager 正常

另开一个容器 shell：

```bash
cd /workspace
source /opt/ros/jazzy/setup.bash
source install/setup.bash

ros2 service list | grep controller_manager
ros2 service call /controller_manager/list_controllers \
  controller_manager_msgs/srv/ListControllers '{}'
```

正常结果应包含：

```text
joint_state_broadcaster: active
diffdrive_controller: active
```

也可以检查 ROS node：

```bash
ros2 node list | sort | grep -E 'controller|robot_state|turtlebot4'
```

如果 `/controller_manager/list_controllers` 服务名存在但调用一直没有结果，通常说明 Gazebo 内部的 controller manager 已经创建了服务接口，但 update loop 或插件执行线程没有正常处理请求。这时继续重启 spawner 意义不大，应优先重启整个 launch 或容器，并检查 Gazebo server 日志。

## 6. 复发时的最小排查步骤

### 6.1 清掉旧进程

同一容器里不要同时存在多套仿真 launch：

```bash
pgrep -af "gz sim|ros2 launch|spawner|rviz2"
```

如果 Ctrl+C 后没有干净退出，直接重启容器：

```bash
docker compose --env-file docker_stuff/.env -f docker_stuff/compose.sim.yaml restart sim
```

### 6.2 先跑 headless

```bash
cd /workspace
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 launch tourbot_bringup sim.launch.py gazebo_gui:=false
```

如果 headless 都不能让 controller active，问题在 server/world/spawn/control 链路，不要先查 GUI。

### 6.3 查 scene

```bash
gz service -s /world/cardboard_city/scene/info \
  --reqtype gz.msgs.Empty \
  --reptype gz.msgs.Scene \
  --timeout 5000 \
  --req '{}'
```

确认至少有：

- `ground_plane`
- `map_walls`
- `standard_dock`
- `turtlebot4`

### 6.4 查 controller

```bash
ros2 service call /controller_manager/list_controllers \
  controller_manager_msgs/srv/ListControllers '{}'
```

确认：

- `joint_state_broadcaster` 是 `active`
- `diffdrive_controller` 是 `active`

### 6.5 再打开 GUI

headless 正常后，再用默认命令打开 GUI：

```bash
ros2 launch tourbot_bringup sim.launch.py
```

如果 GUI 仍然空，但 headless 的 scene 和 controller 都正常，问题集中在 GUI client、camera、OpenGL 或 X11，不是 world 和 controller 链路。

## 7. 这些日志如何理解

下面这些 Gazebo debug 日志不一定表示失败：

```text
[SimulationRunner.cc:551] Creating PostUpdate worker threads
[Sensors.cc:953] Initialization needed
[Sensors.cc:349] Initializing render context
```

它们说明 Gazebo 正在创建仿真更新线程和渲染上下文。真正需要关注的是这些日志之后是否出现：

- `create` spawn robot 成功。
- `/clock` 持续发布。
- `/world/cardboard_city/scene/info` 能看到模型。
- `joint_state_broadcaster` 和 `diffdrive_controller` 变为 `active`。

如果随后出现 spawner 反复超时：

```text
Could not successfully call service /controller_manager/switch_controller
Could not successfully call service /controller_manager/list_controllers
```

处理方向应是：

1. 重启到干净状态。
2. headless 启动验证 server。
3. scene/info 验证 world 和 spawn。
4. list_controllers 验证 `ros2_control`。
5. 最后再处理 GUI 渲染。

不要一开始就只改：

- `xhost`
- spawner timeout
- RViz 配置
- Nav2 参数

这些通常只能改变症状，不能修复 Gazebo server 没稳定起来的问题。

## 8. 仍需注意的问题

当前验证中，Gazebo 在 Ctrl+C 或外层 timeout 结束时，仍可能在 Sensors/render teardown 阶段打印类似 `Segmentation fault` 的退出日志。

这个现象和最初的启动失败不同：

- 如果 scene 已经能看到 world/robot。
- controller 已经 active。
- `/clock` 正常。
- robot 可以被 Nav2 或 `/cmd_vel` 驱动。

那么退出阶段的崩溃更像 Gazebo/渲染插件析构路径问题，不应和启动阶段的空 world、controller timeout 混为一谈。

后续如果要继续提高稳定性，可以再做：

- 对比 `LIBGL_ALWAYS_SOFTWARE=0` 与硬件渲染。
- 对比 Intel/Mesa、NVIDIA runtime 和纯 headless。
- 把 Gazebo server smoke test 固化成脚本或 CI 检查。
- 为 `scene/info` 和 `list_controllers` 增加一键诊断脚本。

## 9. 推荐的最终验收标准

一次启动是否合格，不以 GUI 第一眼是否显示漂亮画面为唯一标准。建议按下面顺序验收：

1. `ros2 launch tourbot_bringup sim.launch.py gazebo_gui:=false` 能稳定启动。
2. `/world/cardboard_city/scene/info` 能看到 `ground_plane`、`map_walls`、`standard_dock`、`turtlebot4`。
3. `/controller_manager/list_controllers` 里 `joint_state_broadcaster` 和 `diffdrive_controller` 都是 `active`。
4. 默认 `ros2 launch tourbot_bringup sim.launch.py` 能打开 GUI。
5. GUI、scene/info 和 controller 状态一致。
6. 需要导航时再打开 `localization:=true nav2:=true rviz:=true`。

只有第 1 到第 3 步通过后，才建议继续查 RViz、AMCL、Nav2 或 GUI 视觉效果。

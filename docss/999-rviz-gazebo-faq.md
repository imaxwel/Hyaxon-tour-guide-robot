# RViz + Gazebo 常见提示与本工程修复记录

更新时间：2026-06-29

## 1. 现象

运行：

```bash
ros2 launch tourbot_bringup sim.launch.py
```

可能看到：

```text
Timed out waiting for transform from base_link to map to become available
Invalid frame ID "map" passed to canTransform argument target_frame
StaticLayer: "map" passed to lookupTransform argument target_frame does not exist
AMCL cannot publish a pose or update the transform. Please set the initial pose...
Message Filter dropping message ... queue is full
```

同时 Gazebo Sim 可能提示“没有响应”，最后 Ctrl+C 后出现一批 `context is invalid`、`planner_server`、`rviz2`、`controller_server` 退出错误。

## 2. 根因梳理

### 2.1 `map` frame 不存在

Nav2 的全局代价地图需要 TF 链：

```text
map -> odom -> base_link -> sensors
```

其中 `map -> odom` 由 AMCL 或 SLAM 发布。没有这个变换时，planner/global_costmap 会持续打印 `map` 不存在。

这次本工程还有一个实际 launch 问题：`tourbot_bringup/launch/sim.launch.py` 原来 include 了 TurtleBot4 的 `turtlebot4_gz.launch.py`，并尝试传入 `nav2/localization/map`。但当前 Jazzy TurtleBot4 的顶层 Gazebo launch 没有可靠把这些参数转发到 navigation launch，导致 localization/Nav2 启动链不稳定。

### 2.2 AMCL 等待初始位姿

这条是正常提示：

```text
AMCL cannot publish a pose or update the transform. Please set the initial pose...
```

AMCL 需要初始位姿后才会稳定发布 `map -> odom`。在 RViz 中用 `2D Pose Estimate` 给机器人点一次初始位姿即可。

### 2.3 Gazebo “没有响应”

主要是资源压力。TurtleBot4 仿真会启动 Gazebo GUI、多个 bridge、传感器、Nav2 和 RViz。若重复运行 launch 或使用 `model:=standard`，CPU/内存压力会很高。

本次验证时重复启动两套 launch 后，容器达到约 700% CPU、接近 1900 个进程/线程，Gazebo GUI 很容易被桌面判定为没有响应。

### 2.4 Ctrl+C 后的大量错误

Ctrl+C 会同时关闭 Gazebo、RViz、Nav2 lifecycle nodes 和 bridge。关闭过程中若某个 node 已经 shutdown，其他 node 还在做 lifecycle transition，就会看到：

```text
rcl node's context is invalid
failed to initialize wait set
Failed to change state for node
process failed to terminate ... escalating to SIGTERM/SIGKILL
```

这些通常是退出阶段噪声，不是启动根因。

## 3. 已修复内容

### 3.1 重写本工程 `sim.launch.py` 的启动结构

现在不再依赖 TurtleBot4 顶层 wrapper 隐式转发导航参数，而是显式启动：

1. Gazebo world
2. TurtleBot4 spawn + bridge + RViz
3. TurtleBot4 localization
4. TurtleBot4 Nav2

这样 `map` 参数能直接传给 localization。

### 3.2 避免重复启动 Nav2

TurtleBot4 spawn launch 自己也支持 `nav2/localization/slam` 参数。为避免顶层参数污染子 launch，本工程把 spawn include 放进 scoped group，并在局部作用域内关闭子 launch 的 navigation：

```text
localization:=false
slam:=false
nav2:=false
```

然后由本工程后面的 explicit include 启动唯一一套 localization/Nav2。

### 3.3 默认模型改为 `lite`

默认模型从 `standard` 改成 `lite`，减少 Gazebo/RViz 资源压力。需要 RGBD camera/OAK-D 时再显式传：

```bash
ros2 launch tourbot_bringup sim.launch.py model:=standard
```

### 3.4 修正 custom world 默认路径

仓库实际文件是：

```text
src/tourbot_bringup/worlds/cardboard_city/world.sdf
```

TurtleBot4 Gazebo launch 会给 `world` 参数追加 `.sdf`，所以默认 custom world 改成不带后缀的 stem：

```text
.../worlds/cardboard_city/world
```

## 4. 推荐启动流程

进入容器：

```bash
docker compose --env-file docker_stuff/.env \
  -f docker_stuff/compose.sim.yaml \
  up -d --force-recreate sim

docker compose --env-file docker_stuff/.env \
  -f docker_stuff/compose.sim.yaml \
  exec sim bash
```

容器内先 build：

```bash
cd /workspace
source /opt/ros/jazzy/setup.bash
colcon build --packages-select tourbot_bringup --symlink-install
source install/setup.bash
```

轻量验证，不开 RViz：

```bash
ros2 launch tourbot_bringup sim.launch.py rviz:=false
```

正常 GUI 使用：

```bash
ros2 launch tourbot_bringup sim.launch.py
```

RViz 打开后：

1. 等 Gazebo world 和 TurtleBot4 完全加载。
2. 如果 Gazebo 暂停，点击 Play。
3. 在 RViz 使用 `2D Pose Estimate` 设置机器人初始位姿。
4. 等 `map -> odom -> base_link` 稳定后再发 Nav2 goal。

## 5. 判断是否正常

另开一个容器 shell：

```bash
source /opt/ros/jazzy/setup.bash
source /workspace/install/setup.bash

ros2 node list | sort | grep -E 'map_server|amcl|planner_server|controller_server'
ros2 topic list | sort | grep -E '^/(clock|map|tf|tf_static|odom|scan)$'
ros2 lifecycle get /map_server
ros2 lifecycle get /amcl
ros2 lifecycle get /planner_server
```

应该只看到一套 `/map_server`、`/amcl`、`/planner_server`、`/controller_server`。如果出现：

```text
there are now at least 2 nodes with the name /map_server
```

说明还有旧 launch 没停干净，先重启容器。

## 6. Gazebo 卡住时的处理

先停止当前 launch。若 Ctrl+C 停不干净，直接重启容器：

```bash
docker compose --env-file docker_stuff/.env \
  -f docker_stuff/compose.sim.yaml \
  restart sim
```

再从轻量模式开始：

```bash
ros2 launch tourbot_bringup sim.launch.py rviz:=false
```

确认稳定后再开 RViz：

```bash
ros2 launch tourbot_bringup sim.launch.py
```

不要同时开多个 `ros2 launch tourbot_bringup sim.launch.py`。这会重复启动 Gazebo、bridge、AMCL 和 Nav2，导致 CPU 飙高、Gazebo GUI 无响应、ROS CLI 卡住。

## 7. 哪些提示可以忽略

短暂出现以下提示通常可以忽略：

```text
Timed out waiting for transform from base_link to map
AMCL cannot publish a pose ... Please set the initial pose
Message Filter dropping message ... queue is full
```

前提是：

1. `/map_server`、`/amcl`、Nav2 nodes 已经启动。
2. RViz 里已经设置过 `2D Pose Estimate`。
3. 之后 `map -> odom -> base_link` 能稳定出现。

如果设置初始位姿后仍持续刷 `map` 不存在，再检查 map_server lifecycle、`/map` topic 和 `/scan` 是否正常。

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

### 3.5 自动发布 AMCL 初始位姿

仅启动 map_server/AMCL/Nav2 还不够。AMCL 没有初始位姿时不会稳定发布 `map -> odom`，Nav2 global_costmap 就会继续刷：

```text
Timed out waiting for transform from base_link to map
Invalid frame ID "map"
```

本工程现在增加了 `tourbot_bringup/initial_pose_publisher`，`sim.launch.py` 会在启动后延迟发布多次 `/initialpose`，等价于自动在 RViz 中点一次 `2D Pose Estimate`。

默认发布：

```text
frame_id: map
x: 0.0
y: 0.0
yaw: 0.0
```

如果用 `x/y/yaw` 改机器人出生点，initial pose 会跟随同一组 launch 参数。

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
3. 默认 launch 会自动发布初始位姿；如果你修改了出生点或地图不匹配，再用 `2D Pose Estimate` 手动修正。
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
Lookup would require extrapolation into the past/future
```

前提是：

1. `/map_server`、`/amcl`、Nav2 nodes 已经启动。
2. 日志里能看到 `tourbot_initial_pose_publisher` 发布 initial pose，或 RViz 里已经设置过 `2D Pose Estimate`。
3. 之后 `map -> odom -> base_link` 能稳定出现。

如果设置初始位姿后仍持续刷 `map` 不存在，再检查 map_server lifecycle、`/map` topic 和 `/scan` 是否正常。

正常自动初始位姿日志类似：

```text
[initial_pose_publisher]: Published initial pose x=0.000 y=0.000 yaw=0.000
[amcl]: initialPoseReceived
[lifecycle_manager_navigation]: Managed nodes are active
```
## 8. 哪些提示可以忽略
是的，你的理解非常准确！这份 `compose.sim.yaml` 实际上**已经把硬件加速和图形界面映射的配置写得很完善了**（甚至考虑到了 Intel 核显的 `iris` 驱动覆盖，以及 `XAUTHORITY` 的权限挂载）。

既然配置文件没问题，但你之前仍然遇到了 `failed to create dri2 screen`（无法创建硬件渲染屏幕）以及 GUI 卡死，**核心原因就是宿主机（你的 Ubuntu 22.04 笔记本）上的环境变量或 X11 访问权限没有成功传递给容器。**

为了让这份配置真正生效，你需要在启动 Docker 容器的**当前宿主机终端**执行以下操作：

### 必须执行的 3 个环境准备步骤

在运行 `docker compose up` 或 `docker compose exec` 之前，请在终端依次执行：

**1. 确认并导出 DISPLAY 变量**
虽然你是在图形界面的终端里操作，但有时候通过某些脚本或特定的 session 进入时，`DISPLAY` 变量可能没被 Docker Compose 捕获。

```bash
# 查看当前 DISPLAY 值，通常是 :0 或 :1
echo $DISPLAY 

# 如果上面的命令没有输出，强制指定它（根据实际情况通常是 :0 或 :1）
export DISPLAY=:0
# 或者
export DISPLAY=:1

```

**2. 开放本地 X11 显示权限 (重点！)**
由于 Docker 容器相当于一个独立的系统，宿主机的图形服务器（X11）默认会拒绝它的渲染请求。

```bash
xhost +local:root

```

*提示：看到 `non-network local connections being added to access control list` 就说明成功了。*

**3. 检查 `.xauth` 文件陷阱（极容易踩坑）**
你看配置里有一行：`- ./.xauth:/tmp/.docker.xauth:ro`。
这是原作者试图用更安全的 Xauthority 机制来代替 `xhost`。**但是，如果你在宿主机的当前目录下没有提前创建一个叫 `.xauth` 的文件，Docker 在启动时会误以为你要挂载一个文件夹，从而自动创建一个名为 `.xauth` 的空文件夹！** 一旦挂载的是文件夹而不是文件，X11 权限验证就会彻底失败，导致 Gazebo 无法出图。

* **检查方法**：在 `compose.sim.yaml` 所在的目录运行 `ls -la .xauth`。如果它显示为一个目录（以 `d` 开头），你需要删掉它，并创建一个空文件：
```bash
rm -rf .xauth
touch .xauth

```



---

### 解答你前一条日志中的疑惑

结合这份完整的 yaml，前一条日志里的那个奇怪报错就真相大白了：

> `groups: cannot find name for group ID 110`

你看 yaml 文件里有：

```yaml
    group_add:
      - "${VIDEO_GID:-44}"
      - "${RENDER_GID:-110}"

```

这个 GID 110 就是 Ubuntu 宿主机上 `render` 用户组的 ID。把容器内的用户加入这个组，是为了让容器有权限读写 `/dev/dri/renderD128`（显卡渲染节点）。因为容器内部原本不存在 110 这个组名，所以系统抛出了那个 warning。**这是一个完全无害的警告**，说明配置生效了，权限已经加上了，请放心忽略。

### 总结你的标准启动流程

以后每次重启电脑后，如果你要运行这个仿真，最稳妥的命令组合是：

```bash
cd /workspace/src/tour-guide-robot/Hyaxon-tour-guide-robot  # 你的项目目录
export DISPLAY=:0          # 或者 :1，取决于 echo $DISPLAY
xhost +local:root          # 放行显示权限
touch .xauth               # 确保 auth 文件存在而非目录
docker compose --env-file docker_stuff/.env -f docker_stuff/compose.sim.yaml up -d
docker compose --env-file docker_stuff/.env -f docker_stuff/compose.sim.yaml exec sim bash

```

进入容器后，再次运行你的 `ros2 launch tourbot_bringup sim.launch.py`，Gazebo 的 GUI 应该就能流畅且带有硬件加速地弹出来了。

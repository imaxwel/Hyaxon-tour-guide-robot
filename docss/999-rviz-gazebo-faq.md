# RViz + Gazebo FAQ 和复发问题处理

更新时间：2026-06-30

## 1. 当前结论

本工程默认启动已改成轻量的项目仿真模式：

```bash
ros2 launch tourbot_bringup sim.launch.py
```

默认会加载 `cardboard_city` Gazebo world、TurtleBot4 robot、必要 bridge 和基础节点，不再默认启动 RViz、AMCL/localization 和完整 Nav2。需要回到 TurtleBot4 官方 warehouse 时显式传：

```bash
ros2 launch tourbot_bringup sim.launch.py use_custom_sim:=false
```

完整导航需要显式打开：

```bash
ros2 launch tourbot_bringup sim.launch.py \
  localization:=true \
  nav2:=true \
  rviz:=true
```

这样做是为了避免在笔记本上一条命令同时启动 Gazebo GUI、RViz、AMCL、Nav2 lifecycle nodes 和多路传感器 bridge，导致 CPU 持续满载后 Gazebo GUI 被桌面判定为“没有响应”。

## 2. 推荐启动流程

宿主机仓库根目录：

```bash
cd /home/imax/4sim/gh-ref/tour-guide-robot/Hyaxon-tour-guide-robot
./docker_stuff/setup-host.bash
docker compose --env-file docker_stuff/.env -f docker_stuff/compose.sim.yaml up -d sim
docker compose --env-file docker_stuff/.env -f docker_stuff/compose.sim.yaml exec sim bash
```

不推荐使用 `xhost +local:` 作为常规流程。优先使用 `setup-host.bash` 生成的 Xauthority。只有 GUI 无法打开时，才临时使用更受限的：

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
```

先跑轻量 Gazebo：

```bash
ros2 launch tourbot_bringup sim.launch.py
```

确认 Gazebo 稳定后，再跑完整导航：

```bash
ros2 launch tourbot_bringup sim.launch.py localization:=true nav2:=true rviz:=true
```

如果完整导航卡顿，保留 Nav2 但关闭 RViz：

```bash
ros2 launch tourbot_bringup sim.launch.py localization:=true nav2:=true rviz:=false
```

## 3. 为什么 Gazebo GUI 仍会无响应

如果容器内：

```bash
glxinfo -B
```

能看到类似：

```text
direct rendering: Yes
OpenGL renderer string: Mesa Intel(R) UHD Graphics
```

说明 X11 和 OpenGL 硬件加速基本正常，Gazebo GUI 无响应通常不是 Docker 显卡权限坏了，而是负载过高。

RViz 里能看到 AMCL/map 周围障碍，不代表 Gazebo 3D world 已经加载了同一套障碍。RViz 显示的是 Nav2/AMCL 使用的 2D 栅格地图；Gazebo 必须在 `world.sdf` 中有对应 3D collision/visual 实体，激光、碰撞和 GUI 才会看到同一个环境。

完整导航会同时运行：

- Gazebo server 和 Gazebo GUI
- RViz
- TurtleBot4 bridge
- LiDAR、RGBD/OAK-D、IR、dock 等传感器 bridge
- map_server、AMCL
- planner、controller、BT navigator、route、smoother、behavior、collision monitor、docking 等 Nav2 节点

在低功耗笔记本上，这些进程叠加后 CPU 会持续满载。桌面环境看到 GUI 主线程响应慢，就会显示“没有响应”。

## 4. 复发时先做这 5 步

1. 停掉旧 launch。如果 Ctrl+C 不干净，直接重启容器：

```bash
docker compose --env-file docker_stuff/.env -f docker_stuff/compose.sim.yaml restart sim
```

2. 进入容器：

```bash
docker compose --env-file docker_stuff/.env -f docker_stuff/compose.sim.yaml exec sim bash
```

3. 检查 GUI/OpenGL：

```bash
glxinfo -B
```

4. 只跑轻量 Gazebo：

```bash
cd /workspace
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 launch tourbot_bringup sim.launch.py
```

5. 另开容器 shell 检查是否重复启动：

```bash
pgrep -af "gz sim|rviz2|ros2 launch|amcl|planner_server|controller_server"
```

同一时间不要存在多套 `ros2 launch tourbot_bringup sim.launch.py`。

## 5. `slam_toolbox` 提示是不是根因

不是。完整导航时 RViz 可能打印：

```text
[rviz2]: Waiting for the slam_toolbox node configuration.
```

如果没有传 `slam:=true`，这通常只是 TurtleBot4 RViz navigation 配置中的面板提示。它不代表必须启动 SLAM，也不是 Gazebo GUI 无响应的根因。

## 6. AMCL 初始位姿提示

完整导航模式会启动 AMCL。AMCL 需要初始位姿后才会稳定发布：

```text
map -> odom
```

本工程会自动发布 `/initialpose`。正常日志类似：

```text
[tourbot_initial_pose_publisher]: Published initial pose x=0.000 y=0.000 yaw=0.000
[amcl]: initialPoseReceived
[lifecycle_manager_navigation]: Managed nodes are active
```

短暂出现下面提示可以忽略：

```text
Lookup would require extrapolation into the future
Timed out waiting for transform from base_link to map
AMCL cannot publish a pose or update the transform
```

前提是后续能看到 `initialPoseReceived`，并且 lifecycle nodes 变成 active。

## 7. `--build` 什么时候需要

首次构建或 Dockerfile/entrypoint/镜像依赖改变后：

```bash
docker compose --env-file docker_stuff/.env -f docker_stuff/compose.sim.yaml up -d --build sim
```

日常已经 build 过以后：

```bash
docker compose --env-file docker_stuff/.env -f docker_stuff/compose.sim.yaml up -d sim
```

改源码通常不需要 rebuild Docker image，因为仓库通过 bind mount 挂到容器的 `/workspace`。改 ROS 包后在容器内重新：

```bash
colcon build --packages-select tourbot_bringup --symlink-install
```

## 8. 判断系统是否正常

另开容器 shell：

```bash
source /opt/ros/jazzy/setup.bash
source /workspace/install/setup.bash

ros2 topic echo --once /clock
ros2 topic list | sort | grep -E '^/(clock|tf|tf_static|odom|scan|map)$'
ros2 node list | sort
```

完整导航模式再检查：

```bash
ros2 lifecycle get /map_server
ros2 lifecycle get /amcl
ros2 lifecycle get /planner_server
ros2 lifecycle get /controller_server
```

如果出现同名节点警告，例如至少两个 `/map_server`，说明旧 launch 没停干净。重启容器后再测。

## 9. 退出和清理

停止当前 launch 优先用 Ctrl+C。

如果 Gazebo/RViz 不响应或 Ctrl+C 后还有残留进程：

```bash
docker compose --env-file docker_stuff/.env -f docker_stuff/compose.sim.yaml restart sim
```

停止容器但保留 image 和 cache volume：

```bash
docker compose --env-file docker_stuff/.env -f docker_stuff/compose.sim.yaml stop sim
```

删除容器：

```bash
docker compose --env-file docker_stuff/.env -f docker_stuff/compose.sim.yaml down
```

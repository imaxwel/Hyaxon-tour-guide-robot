# Gazebo + RViz 仿真环境检查与启动步骤

## 1. 结论

当前工程有 Gazebo + RViz 仿真相关入口，但不是一个已经完整闭环验证过的自定义导览仿真环境。

已经存在的部分：

- `src/tourbot_bringup/launch/sim.launch.py`
  - 包装了 TurtleBot4 官方 Gazebo bringup：`turtlebot4_gz_bringup/launch/turtlebot4_gz.launch.py`
  - 默认传入：
    - `nav2:=true`
    - `slam:=false`
    - `localization:=true`
    - `rviz:=true`
  - 因此它的目标是一次性启动 Gazebo、TurtleBot4 仿真、Nav2 localization、Nav2 navigation 和 RViz。

- `src/tourbot_bringup/launch/robot.launch.py`
  - 启动 localization、Nav2 和 RViz。
  - 它不是 Gazebo 启动文件，适合实体机器人或已经单独启动仿真机器人后再启动导航可视化。

- `src/tourbot_bringup/worlds/cardboard_city/world.sdf`
  - 有一个 Gazebo SDF world 文件。
  - 目前内容主要是 physics、Gazebo system plugins、GUI 配置、光源和 ground plane。
  - 没有看到完整墙体、场景模型、AprilTag 模型或和 `map_area.yaml` 严格对应的环境几何。

- `src/tourbot_bringup/maps/cardboard_city/map_area.yaml`
  - 有一张 Nav2 localization 用的 occupancy map。

当前需要注意的问题：

- `cardboard_city` Gazebo world 现在包含从 `map_area.pgm` 生成的静态墙体，能和 Nav2/AMCL 的 2D map 对齐。
- `sim.launch.py` 的 `custom_world` 默认值指向：

  ```text
  worlds/cardboard_city/world
  ```

  但仓库里实际文件是：

  ```text
  worlds/cardboard_city/world.sdf
  ```

  所以 `use_custom_sim:=true` 不带额外参数时会找不到默认自定义 world。

- `tourbot_bringup/package.xml` 只声明了 launch 相关依赖，没有声明 `turtlebot4_gz_bringup`、`turtlebot4_navigation`、`turtlebot4_viz`、`nav2_*`、`ros_gz_sim` 等运行依赖。`rosdep install --from-paths src` 不一定能帮你装全仿真依赖。

- 当前机器检查到的 ROS 版本是 Humble，但项目 README 写的是 ROS 2 Jazzy + Gazebo Harmonic。不要把 Humble 和 Jazzy 的 TurtleBot4/Gazebo 包混装在同一个 shell 里测试。

一句话判断：

> 有仿真启动入口，有 RViz/Nav2/Gazebo 集成意图；默认 TurtleBot4 仿真可以按 TurtleBot4 包启动。项目自定义 `cardboard_city` Gazebo world 目前不完整，且启动参数默认路径有问题，需要修正或显式传参后才能用于自定义场景。

## 2. 参考资料

建议优先按官方版本组合使用：

- TurtleBot4 simulator 安装说明：<https://turtlebot.github.io/turtlebot4-user-manual/software/turtlebot4_simulator.html>
- TurtleBot4 simulation 说明：<https://turtlebot.github.io/turtlebot4-user-manual/software/simulation.html>
- TurtleBot4 Navigator 示例，包含 `turtlebot4_gz_bringup` + Nav2 + RViz 启动命令：<https://turtlebot.github.io/turtlebot4-user-manual/tutorials/turtlebot4_navigator.html>
- Gazebo 从 ROS 2 launch 启动：<https://gazebosim.org/docs/latest/ros2_launch_gazebo/>
- ROS 2 Jazzy 与 Gazebo Harmonic vendor packages：<https://gazebosim.org/docs/latest/ros2_gz_vendor_pkgs/>
- Nav2 Gazebo setup guide：<https://docs.nav2.org/setup_guides/gazebo.html>

## 3. 推荐环境

项目 README 写的是：

- ROS 2 Jazzy
- Gazebo Harmonic
- TurtleBot4 packages
- Nav2
- RViz2
- SLAM Toolbox
- apriltag_ros
- TF2

推荐使用 Ubuntu 24.04 + ROS 2 Jazzy。TurtleBot4 官方 simulator metapackage 对应命令通常是：

```bash
sudo apt update
sudo apt install ros-jazzy-turtlebot4-simulator ros-jazzy-irobot-create-nodes
```

如果只验证 Gazebo/ROS 集成，Jazzy 下 Gazebo vendor packages 的基础检查可以是：

```bash
sudo apt install ros-jazzy-gz-tools-vendor ros-jazzy-gz-sim-vendor
source /opt/ros/jazzy/setup.bash
gz sim --help
```

工程级最佳实践：

- 同一个 shell 只 source 一个 ROS distro。
- Jazzy 项目用 `/opt/ros/jazzy/setup.bash`。
- Humble 项目用 `/opt/ros/humble/setup.bash`。
- 不要先 source Humble 再 source Jazzy。
- GUI 仿真机器建议有独立显卡；CI 或服务器建议用 headless Gazebo server。

## 4. 启动前检查

在 workspace 根目录执行：

```bash
cd /home/imax/4sim/gh-ref/tour-guide-robot/Hyaxon-tour-guide-robot
```

确认 ROS 版本：

```bash
source /opt/ros/jazzy/setup.bash
echo "$ROS_DISTRO"
```

期望输出：

```text
jazzy
```

确认 TurtleBot4 仿真包存在：

```bash
ros2 pkg prefix turtlebot4_gz_bringup
ros2 pkg prefix turtlebot4_navigation
ros2 pkg prefix turtlebot4_viz
```

确认 TurtleBot4 Gazebo launch 支持的参数：

```bash
ros2 launch turtlebot4_gz_bringup turtlebot4_gz.launch.py --show-args
```

重点看是否支持这些参数：

- `nav2`
- `slam`
- `localization`
- `rviz`
- `world`
- `map`
- `model`

如果某些参数不存在，说明你安装的 TurtleBot4 版本和本项目 `sim.launch.py` 预期不一致。先按 `--show-args` 的实际结果调整命令，不要盲目继续。

确认本工程 ROS packages 能被 colcon 识别：

```bash
colcon list
```

当前仓库应至少看到：

```text
apriltag
apriltag_msgs
apriltag_ros
tourbot_behaviors
tourbot_bringup
tourbot_interfaces
tourbot_landmarks
tourbot_mission
tourbot_perception
```

## 5. 构建工程

安装依赖：

```bash
source /opt/ros/jazzy/setup.bash
rosdep update
rosdep install --from-paths src --ignore-src -r -y --rosdistro jazzy -t buildtool -t build -t exec
```

注意：这里跳过 test-only 依赖，避免 lint/test 包阻塞仿真容器依赖安装。

构建：

```bash
colcon build --symlink-install
```

source workspace：

```bash
source install/setup.bash
```

确认本工程 launch 可见：

```bash
ros2 pkg prefix tourbot_bringup
ros2 launch tourbot_bringup sim.launch.py --show-args
```

## 6. 推荐启动方式 A：启动默认项目 Gazebo 仿真

这是当前工程最接近“一键仿真”的入口。

终端 1：

```bash
cd /home/imax/4sim/gh-ref/tour-guide-robot/Hyaxon-tour-guide-robot
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 launch tourbot_bringup sim.launch.py
```

这个命令默认走 `use_custom_sim:=true`，也就是加载项目自带 `cardboard_city` Gazebo world。默认只启动 Gazebo、TurtleBot4、bridge 和基础节点；Nav2、localization 和 RViz 需要显式传参打开。

等 Gazebo 和 RViz 打开后：

1. 如果 Gazebo 左下角是暂停状态，点击 Play。
2. 在 RViz 里确认 Fixed Frame 通常是 `map`。
3. 如果 AMCL 没有初始位姿，使用 `2D Pose Estimate` 给机器人设置初始位姿。
4. 使用 `Nav2 Goal` 发送一个短距离目标，验证路径规划和控制链路。

对照官方命令，等价的 TurtleBot4 直接启动方式是：

```bash
ros2 launch turtlebot4_gz_bringup turtlebot4_gz.launch.py nav2:=true slam:=false localization:=true rviz:=true
```

如果工程的 `sim.launch.py` 启动失败，但上面的官方命令能启动，优先检查 `tourbot_bringup/launch/sim.launch.py` 和你本机 TurtleBot4 包的 launch 参数是否匹配。

## 7. 推荐启动方式 B：使用工程自带 cardboard_city map/world

当前可以直接执行：

```bash
ros2 launch tourbot_bringup sim.launch.py use_custom_sim:=true
```

`sim.launch.py` 的默认 custom world stem 已指向 `worlds/cardboard_city/world`，SDF world name 使用 `cardboard_city`。

终端 1：

```bash
cd /home/imax/4sim/gh-ref/tour-guide-robot/Hyaxon-tour-guide-robot
source /opt/ros/jazzy/setup.bash
source install/setup.bash

WORLD_STEM="$(ros2 pkg prefix --share tourbot_bringup)/worlds/cardboard_city/world"
MAP_YAML="$(ros2 pkg prefix --share tourbot_bringup)/maps/cardboard_city/map_area.yaml"

ros2 launch tourbot_bringup sim.launch.py \
  use_custom_sim:=true \
  custom_world:="$WORLD_STEM" \
  custom_map:="$MAP_YAML"
```

这里故意使用 `WORLD_STEM`，也就是不带 `.sdf` 后缀的路径。部分 TurtleBot4 Gazebo launch 会在内部给 `world` 参数追加 `.sdf`。如果你的 `--show-args` 或实际 launch 实现要求完整 SDF 路径，则改成：

```bash
WORLD_SDF="$(ros2 pkg prefix --share tourbot_bringup)/worlds/cardboard_city/world.sdf"
```

并把 `custom_world:="$WORLD_STEM"` 替换成：

```bash
custom_world:="$WORLD_SDF"
```

如果仍失败，先不要调 Nav2，先单独验证 Gazebo 能否打开该 SDF。

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash

WORLD_SDF="$(ros2 pkg prefix --share tourbot_bringup)/worlds/cardboard_city/world.sdf"
ros2 launch ros_gz_sim gz_sim.launch.py gz_args:="$WORLD_SDF -r -v 4"
```

这只验证 Gazebo world 是否有效，不会自动 spawn TurtleBot4，也不会自动启动 Nav2/RViz。

## 8. 启动导览任务

导览任务不是 Gazebo/RViz 的必要组成部分。只有在下面条件都满足时才建议启动：

- Gazebo 中已经有可导航的 TurtleBot4。
- Nav2 已经 active。
- RViz 能看到 map、robot、TF、local/global costmap。
- 仿真 camera topic 与 `tourbot_perception/launch/apriltag_pipeline.launch.py` 的 remap 匹配：
  - `/oakd/rgb/preview/image_raw`
  - `/oakd/rgb/preview/camera_info`
- Gazebo world 里有和 `tourbot_landmarks/config/cardboard_city/landmarks.yaml` 对应的 AprilTag。

终端 2：

```bash
cd /home/imax/4sim/gh-ref/tour-guide-robot/Hyaxon-tour-guide-robot
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 launch tourbot_bringup mission.launch.py
```

当前仓库的自定义 world 没有完整 AprilTag 场景，默认 TurtleBot4 world 也不一定和 `cardboard_city` landmarks 匹配。因此 `mission.launch.py` 可以作为节点集成测试入口，但不能证明完整导览仿真已经可用。

## 9. 启动后的验证清单

### 9.1 进程和节点

```bash
ros2 node list
```

重点确认是否有类似节点：

```text
/rviz2
/map_server
/amcl
/bt_navigator
/controller_server
/planner_server
/behavior_server
/waypoint_follower
```

Gazebo/TurtleBot4 相关节点名称会随版本变化，不要死记名称。关键是确认 Gazebo、robot state、bridge、Nav2 lifecycle nodes 都存在。

### 9.2 Topic

```bash
ros2 topic list
```

重点确认：

```text
/clock
/tf
/tf_static
/map
/odom
/scan
/cmd_vel
```

如果要跑 AprilTag perception，还要确认：

```text
/oakd/rgb/preview/image_raw
/oakd/rgb/preview/camera_info
```

检查仿真时间：

```bash
ros2 topic echo --once /clock
```

检查 map 是否发布：

```bash
ros2 topic echo --once /map
```

检查 laser scan：

```bash
ros2 topic hz /scan
```

检查 camera：

```bash
ros2 topic hz /oakd/rgb/preview/image_raw
ros2 topic echo --once /oakd/rgb/preview/camera_info
```

### 9.3 TF

安装过 `tf2_tools` 时：

```bash
ros2 run tf2_tools view_frames
```

重点检查链路是否连通：

```text
map -> odom -> base_link -> sensors
```

常见失败：

- RViz 报 `No transform from [base_link] to [map]`
- `map -> odom` 不存在，通常是 localization/AMCL 未正常工作
- `odom -> base_link` 不存在，通常是机器人仿真/bridge/robot state 链路异常

### 9.4 Nav2 lifecycle

```bash
ros2 lifecycle nodes
```

Nav2 相关 lifecycle node 应进入 `active`。如果没有 active，可以看 launch 日志，或逐个检查：

```bash
ros2 lifecycle get /map_server
ros2 lifecycle get /amcl
ros2 lifecycle get /controller_server
ros2 lifecycle get /planner_server
ros2 lifecycle get /bt_navigator
```

### 9.5 RViz 操作验证

在 RViz 中：

1. Fixed Frame 设为 `map`。
2. 确认能看到 map。
3. 确认能看到 robot model。
4. 确认 laser scan 或 costmap 正常刷新。
5. 使用 `2D Pose Estimate` 设置初始位姿。
6. 使用 `Nav2 Goal` 发送短距离目标。
7. 观察：
   - global path 是否生成
   - local costmap 是否更新
   - robot 是否移动
   - Gazebo 里机器人是否同步运动

## 10. 常见问题

### 10.1 `Package 'turtlebot4_gz_bringup' not found`

原因：没有安装 TurtleBot4 simulator，或 shell 没有 source 正确 ROS distro。

处理：

```bash
source /opt/ros/jazzy/setup.bash
sudo apt install ros-jazzy-turtlebot4-simulator ros-jazzy-irobot-create-nodes
```

然后重新打开终端，重新 source。

### 10.2 `cardboard_city.sdf` 找不到

历史原因：旧版 `sim.launch.py` 默认路径和仓库实际文件名不一致。当前默认值已修复为 `worlds/cardboard_city/world`。

当前仓库实际文件：

```text
src/tourbot_bringup/worlds/cardboard_city/world.sdf
```

如果再次出现类似错误，检查是否已重新 build 并 `source install/setup.bash`。

### 10.3 Gazebo 有机器人，RViz 没有 map 或机器人

优先检查：

```bash
ros2 topic echo --once /clock
ros2 topic echo --once /map
ros2 topic list | grep tf
ros2 lifecycle get /amcl
```

常见原因：

- `use_sim_time` 没有统一。
- map yaml 路径不对。
- AMCL 没有初始位姿。
- TF bridge 或 robot state publisher 没起来。
- Gazebo 暂停，没有发布仿真时间。

### 10.4 RViz 有 map，Nav2 goal 不动

优先检查：

```bash
ros2 lifecycle get /bt_navigator
ros2 lifecycle get /controller_server
ros2 topic hz /scan
ros2 topic echo --once /odom
ros2 topic echo --once /cmd_vel
```

常见原因：

- costmap 没有 sensor data。
- controller server 未 active。
- robot footprint 或 inflation 参数导致目标不可达。
- 初始位姿偏差过大。
- Gazebo 处于暂停状态。

### 10.5 mission 启动后卡住或 AprilTag 永远找不到

当前 perception launch 固定使用：

```text
/oakd/rgb/preview/image_raw
/oakd/rgb/preview/camera_info
```

先检查仿真是否真的发布这些 topic：

```bash
ros2 topic list | grep oakd
ros2 topic hz /oakd/rgb/preview/image_raw
```

再检查 world 中是否真的有 AprilTag 模型，并且 tag ID、尺寸、朝向、可见距离和 `tourbot_perception/config/apriltags_36h11.yaml`、`tourbot_landmarks/config/cardboard_city/landmarks.yaml` 对得上。

## 11. 行业最佳实践建议

### 11.1 明确区分 hardware bringup 和 sim bringup

推荐保留两个入口：

- `robot.launch.py`
  - 实体机器人或外部仿真已存在时使用。
  - 只启动 localization、Nav2、RViz、mission 相关节点。

- `sim.launch.py`
  - 仿真专用。
  - 负责启动 Gazebo、spawn robot、bridge、robot state、Nav2、RViz。

不要让一个 launch 文件同时隐式适配实体机器人和仿真环境，否则后期排查 TF、topic 和 clock 问题会很困难。

### 11.2 所有路径参数化

推荐所有可变资源都暴露为 launch arguments：

- `world`
- `map`
- `nav2_params`
- `rviz_config`
- `landmarks`
- `robot_model`
- `x`
- `y`
- `z`
- `yaw`
- `use_sim_time`
- `headless`

这样可以做：

```bash
ros2 launch tourbot_bringup sim.launch.py \
  world:=cardboard_city \
  map:=/path/to/map_area.yaml \
  landmarks:=/path/to/landmarks.yaml \
  rviz:=true \
  headless:=false
```

### 11.3 world、map、landmarks 必须成套管理

一个可用的导览仿真环境至少应包含：

```text
environment_name/
├── world.sdf
├── map_area.yaml
├── map_area.pgm
├── landmarks.yaml
├── rviz.rviz
└── README.md
```

其中：

- `world.sdf` 是 Gazebo 真实几何和视觉场景。
- `map_area.pgm/yaml` 是 Nav2 localization 用的 2D occupancy map。
- `landmarks.yaml` 是任务层导航点和 AprilTag 语义。
- RViz config 固定显示 map、TF、laser、robot、costmaps 和 Nav2 tools。

最佳实践是把这三者作为同一个版本化环境包处理。只改 world 不改 map，或者只改 landmarks 不改 world，都会导致仿真看似能启动但任务失败。

### 11.4 统一 `use_sim_time`

Gazebo 仿真必须统一使用 `/clock`。

Nav2、robot state publisher、perception、mission、RViz 都应使用：

```yaml
use_sim_time: true
```

排查时先看：

```bash
ros2 param get /rviz2 use_sim_time
ros2 param get /bt_navigator use_sim_time
ros2 topic echo --once /clock
```

### 11.5 在 package.xml 声明运行依赖

`tourbot_bringup/package.xml` 建议补充仿真相关 exec dependencies。具体包名要按目标 ROS distro 确认，典型包括：

```xml
<exec_depend>turtlebot4_gz_bringup</exec_depend>
<exec_depend>turtlebot4_navigation</exec_depend>
<exec_depend>turtlebot4_viz</exec_depend>
<exec_depend>nav2_bringup</exec_depend>
<exec_depend>rviz2</exec_depend>
<exec_depend>ros_gz_sim</exec_depend>
```

这样 `rosdep install --from-paths src --ignore-src` 才能更接近真实运行依赖。

### 11.6 提供 headless 模式

CI 或远程服务器通常没有 GUI。推荐在 `sim.launch.py` 提供：

```text
headless:=true
rviz:=false
```

对应只启动 Gazebo server，不启动 GUI 和 RViz。

可参考 Gazebo 官方方式：

```bash
ros2 launch ros_gz_sim gz_server.launch.py world_sdf_file:=/path/to/world.sdf
```

### 11.7 加 launch smoke test

至少做一个自动化冒烟测试：

1. headless 启动 Gazebo。
2. spawn robot。
3. 等待 `/clock`。
4. 等待 `/tf`。
5. 等待 `/scan`。
6. 等待 Nav2 lifecycle active。
7. 发送一个短距离导航目标。
8. 断言机器人 odom 有变化。

这类测试不要求完整导览成功，但能防止启动文件、依赖、topic remap、TF 和 sim time 被改坏。

### 11.8 让 AprilTag 仿真可验证

如果 mission 要在 Gazebo 中闭环，world 中需要显式建模 AprilTag：

- tag family 和配置一致，例如 `36h11`。
- tag ID 和 `landmarks.yaml` 一致。
- tag 尺寸和 detector 参数一致。
- tag 朝向让 OAK-D 能在合理距离内看到。
- 光照不要让 tag 过曝或过暗。
- 每个 tag 的 Gazebo pose、map pose、landmark pose 要有一致坐标关系。

建议给 AprilTag detection 单独提供验证命令：

```bash
ros2 topic echo /detections
ros2 run rqt_image_view rqt_image_view
```

如果没有图像 topic 或没有检测输出，不要先调 mission 逻辑。

## 12. 建议的后续代码修正

建议后续单独提交这些修正：

1. 保持 `sim.launch.py` 的 `custom_world` stem 和 `world.sdf` 文件名一致。
   - 当前默认：`worlds/cardboard_city/world`
   - 当前实际：`worlds/cardboard_city/world.sdf`

2. 明确 TurtleBot4 `world` 参数期望。
   - 如果 TurtleBot4 launch 期望 world stem，则默认值不要带 `.sdf`。
   - 如果期望完整路径，则默认值使用完整 `.sdf`。

3. 给 `tourbot_bringup/package.xml` 补齐运行依赖。

4. 给 `sim.launch.py` 增加：
   - `headless`
   - `rviz`
   - `nav2`
   - `slam`
   - `localization`
   - `map`
   - `world`
   - `nav2_params`
   - `use_sim_time`

5. 给 `cardboard_city` world 补齐真实场景：
   - 墙体和障碍物
   - AprilTag 模型
   - 与 `map_area.yaml` 对齐的坐标
   - 与 `landmarks.yaml` 对齐的 landmark pose

6. 增加 RViz config 文件，例如：

   ```text
   src/tourbot_bringup/rviz/cardboard_city.rviz
   ```

7. 增加 headless launch test，防止后续改动破坏仿真启动。

## 13. 最小可执行命令汇总

默认 TurtleBot4 仿真：

```bash
cd /home/imax/4sim/gh-ref/tour-guide-robot/Hyaxon-tour-guide-robot
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install
source install/setup.bash
ros2 launch tourbot_bringup sim.launch.py
```

尝试工程自带 custom world：

```bash
cd /home/imax/4sim/gh-ref/tour-guide-robot/Hyaxon-tour-guide-robot
source /opt/ros/jazzy/setup.bash
source install/setup.bash

WORLD_STEM="$(ros2 pkg prefix --share tourbot_bringup)/worlds/cardboard_city/world"
MAP_YAML="$(ros2 pkg prefix --share tourbot_bringup)/maps/cardboard_city/map_area.yaml"

ros2 launch tourbot_bringup sim.launch.py \
  use_custom_sim:=true \
  custom_world:="$WORLD_STEM" \
  custom_map:="$MAP_YAML"
```

只验证 Gazebo 能否打开工程 SDF：

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash
WORLD_SDF="$(ros2 pkg prefix --share tourbot_bringup)/worlds/cardboard_city/world.sdf"
ros2 launch ros_gz_sim gz_sim.launch.py gz_args:="$WORLD_SDF -r -v 4"
```

在仿真和 Nav2 正常后启动导览任务：

```bash
cd /home/imax/4sim/gh-ref/tour-guide-robot/Hyaxon-tour-guide-robot
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 launch tourbot_bringup mission.launch.py
```

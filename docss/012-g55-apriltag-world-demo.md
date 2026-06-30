# 012 · G55 AprilTag world 补全与门流程演示

> 日期：2026-06-30  
> 目标：在 `cardboard_city` 仿真 world 中补齐 AprilTag 资产，并提供可重复的“门 tag 可见 = 门关闭、tag 消失 = 门打开、随后穿门”演示入口。

## 1.本次补齐内容

### 1.1 生成 8 个 AprilTag 36h11 模型

模型目录：

```text
src/tourbot_bringup/worlds/cardboard_city/models/
  tag36_11_00000/
  tag36_11_00001/
  ...
  tag36_11_00007/
```

每个模型包含：

```text
model.sdf
model.config
materials/textures/tag36_11_XXXXX.png
thumbnails/tag36_11_XXXXX.png
```

关键约束：

- SDF 版本：`1.9`
- 物理边长：`0.162 m`
- tag family：`36h11`
- 纹理来源：`AprilRobotics/apriltag-imgs`

这与当前配置保持一致：

```text
src/tourbot_perception/config/apriltags_36h11.yaml
family: 36h11
size: 0.162
```

### 1.2 include 到 `world.sdf`

修改文件：

```text
src/tourbot_bringup/worlds/cardboard_city/world.sdf
```

已加入：

- `apriltag_home_0`
- `apriltag_door_outward_1`
- `apriltag_door_inward_2`
- `apriltag_goal_3`
- `apriltag_goal_4`
- `apriltag_goal_5`
- `apriltag_goal_6`
- `apriltag_goal_7`

摆放原则：

- `landmarks.yaml` 中的坐标按“机器人观察 pose”处理。
- tag 放在观察 pose 前方约 `0.45 m`。
- tag 法线朝向机器人。
- 门板、纸箱、边界墙先做视觉几何，不加碰撞，避免开环穿门动作被静态门板挡住。

## 2.修复 custom world 启动方式

原问题：

TurtleBot4 下游 launch 会把 `world` 参数同时当作：

- Gazebo 要加载的 world 文件名；
- ROS-GZ bridge topic 中的 world name。

如果直接传绝对路径，会生成非法 topic，例如：

```text
/world//ws/install/.../world/model/turtlebot4/...
```

这会导致 `ros_gz_bridge` 解析 remap rule 失败。

当前修复：

- `tourbot_bringup/launch/sim.launch.py` 的 custom 分支改为直接启动 `ros_gz_sim`，用绝对 SDF 路径加载 world。
- TurtleBot4 spawn / bridge 使用合法 world name：`world_demo`。
- 增加 `custom_world_name` 参数。
- 增加 `custom_gz_args` 参数。
- 增加 `start_navigation` 参数，默认 `true`；门 demo 时建议设为 `false`。
- 自动设置 `GZ_SIM_RESOURCE_PATH` / `IGN_GAZEBO_RESOURCE_PATH`，让 Gazebo 能找到 `models/tag36_11_00000..00007`。

## 3.稳定门流程 demo

新增 launch：

```text
src/tourbot_bringup/launch/door_apriltag_demo.launch.py
```

新增节点：

```text
src/tourbot_mission/tourbot_mission/door_apriltag_demo_node.py
```

它会启动并驱动现有三个 action server：

- `/align_to_apriltag`
- `/wait_for_tag_removed`
- `/door_traverse`

演示逻辑：

1. 发布 `/oakd/rgb/preview/camera_info`。
2. 发布 `/detections`，让门 tag `tag_id=1` 可见，表示门关闭。
3. 调用 `/align_to_apriltag`，对齐到 tag。
4. 调用 `/wait_for_tag_removed`，先保持 tag 可见 `2.0s`，再停止发布该 tag，表示门打开。
5. 调用 `/door_traverse`，执行穿门。

为了让演示不受 Gazebo controller 抖动影响，demo launch 中的 `door_behavior_server` 使用 `/door_demo/odom`，由 demo 节点根据 `/cmd_vel` 积分发布。真实 `mission.launch.py` 不受影响，仍使用真实/仿真 `/odom`。

## 4.运行命令

推荐两个终端，使用同一个 `ROS_DOMAIN_ID`。下面用 `77` 避免和已有仿真串话。

终端 A：启动 custom world + TurtleBot4，不启动 Nav2/RViz。

```bash
cd ~/4sim/gh-ref/tour-guide-robot/Hyaxon-tour-guide-robot
docker compose -f docker_stuff/compose.yaml run --rm --no-deps dev bash -lc '
  source install/setup.bash
  export ROS_DOMAIN_ID=77
  ros2 launch tourbot_bringup sim.launch.py \
    use_custom_sim:=true \
    start_navigation:=false \
    custom_gz_args:="-r -s -v 2"
'
```

终端 B：启动门 AprilTag demo。

```bash
cd ~/4sim/gh-ref/tour-guide-robot/Hyaxon-tour-guide-robot
docker compose -f docker_stuff/compose.yaml run --rm --no-deps dev bash -lc '
  source install/setup.bash
  export ROS_DOMAIN_ID=77
  ros2 launch tourbot_bringup door_apriltag_demo.launch.py tag_id:=1
'
```

预期关键日志：

```text
align_to_apriltag succeeded: Aligned to tag 1.
Door is CLOSED: publishing visible AprilTag 1 for 2.0s.
Door is OPEN: AprilTag is no longer visible.
wait_for_tag_removed succeeded: Tag 1 removed from FOV for 1.55 seconds.
door_traverse succeeded: Door traversal complete for tag_id=1, door_type=OUTWARD
Door AprilTag demo complete: closed tag detected, tag removed, and door traversal finished.
```

## 5.验证结果

已在远端 `xiao-5080` 的 Docker 环境验证：

- `colcon build --symlink-install --packages-select tourbot_bringup tourbot_mission` 通过。
- `sim.launch.py use_custom_sim:=true start_navigation:=false custom_gz_args:="-r -s -v 2"` 能启动 `world_demo`，并创建合法 `/world/world_demo/...` bridge。
- `/odom` 在 2 秒内出现。
- `door_apriltag_demo.launch.py tag_id:=1` 在 15 秒内完整返回成功。

## 6.边界说明

当前稳定 demo 使用可控 `/detections` 消息来表达“门关闭/打开”，不是依赖 Gazebo 相机实际识别 tag 纹理。这是为了稳定验证门行为链路：

```text
detections -> align_to_apriltag -> wait_for_tag_removed -> door_traverse
```

world 中已经有真实 8 个 AprilTag 可视模型。若要进一步做完整视觉闭环，需要单独调试：

- OAK-D Gazebo 相机视角是否正对 tag。
- tag 纹理在 `gz sim` / OGRE2 中是否清晰、未镜像。
- `apriltag_ros` 是否能从 `/oakd/rgb/preview/image_raw` 发布真实 `/detections`。
- 门 opening 事件如何驱动 Gazebo 中真实 tag/门板消失或移动。

也就是说，本次已经补齐 world 资产和门行为演示闭环；真实视觉识别闭环是下一层集成验证。

# 05 二次开发指南：在本工程上加你自己的功能

> 适用对象：1-3 个月 ROS 2 初学者
> 目标：能在本工程上完成 4 类典型扩展：加 landmark、加新地图、改行为参数、写新行为。

---

## 0.先掌握 3 个必备工作流

无论改什么，下面这 3 步都会反复用：

```bash
# 1.在主机准备容器外的修改（用编辑器）
vim src/.../xxx.py

# 2.进容器重新构建（增量）
cd /home/xiaozy/4sim/gh-ref/tour-guide-robot/Hyaxon-tour-guide-robot
docker compose -f docker_stuff/compose.yaml run --rm build

# 3.重启对应服务
docker compose -f docker_stuff/compose.yaml --profile mission up -d --force-recreate mission
```

> 注意：本工程把 `/ws/build`、`/ws/install`、`/ws/log` 挂到 Docker 命名卷，宿主仓库根目录下的 `build/install/log` 不是真正的构建产物路径。

---

## 1.改 landmark / 加新地标

### 1.1 文件位置

```text
src/tourbot_landmarks/config/cardboard_city/landmarks.yaml
```

### 1.2 字段含义

```yaml
home:
  tag_id: 0          # 起点 tag，可不实际贴
  x: 0
  y: 0
  theta: NORTH       # 方向枚举，见下表

landmarks:
  - name: goal_3     # 任意字符串，仅作日志
    tag_id: 3        # 必须和场景里真实贴的 tag 对应
    x: 0.942         # map 坐标系 X（米）
    y: 0.495         # map 坐标系 Y（米）
    theta: WEST      # 到达点朝向
```

方向枚举来自 `turtlebot4_navigation.turtlebot4_navigator.TurtleBot4Directions`：

```text
NORTH       =   0
NORTH_WEST  =  45
WEST        =  90
SOUTH_WEST  = 135
SOUTH       = 180
SOUTH_EAST  = 225
EAST        = 270
NORTH_EAST  = 315
```

### 1.3 门规则（硬编码，改前先理解）

```text
tag_id == 1   →  outward door：到点后等 tag 消失，前进
tag_id == 2   →  inward  door：到点后等 tag 消失，先后退/转身再前进
其它 tag       →  普通 landmark：对齐 → 旋转 180°
```

逻辑在 `tour_deliberation_node.py` 的 `is_door_tag()`：

```python
def is_door_tag(tag_id: int) -> bool:
    return tag_id in (1, 2)
```

想加新门，要么沿用 `tag_id ∈ {1, 2}`，要么改这个函数。

### 1.4 验收

```bash
# 进 dev 容器
docker compose -f docker_stuff/compose.yaml run --rm --no-deps dev bash
source install/setup.bash
python3 -c "
from tourbot_landmarks.landmarks_loader import load_landmarks
import yaml
print(yaml.safe_dump(load_landmarks('cardboard_city')))
"
```

应能干净打印出你的新 landmark。

---

## 2.换地图

### 2.1 准备 map 文件

把 SLAM 或手画的地图放到：

```text
src/tourbot_bringup/maps/<my_map>/map_area.pgm
src/tourbot_bringup/maps/<my_map>/map_area.yaml
```

### 2.2 准备 landmark 文件

```text
src/tourbot_landmarks/config/<my_map>/landmarks.yaml
```

### 2.3 改 mission 节点中的 map_name

`tour_deliberation_node.py`：

```python
map_name = "cardboard_city"     # 改成 "<my_map>"
landmark_data = load_landmarks(map_name)
```

> 进阶：把 `map_name` 改成 ROS 参数，启动时通过 `ros2 run ... --ros-args -p map_name:=my_map` 传入，无需改代码。

### 2.4 启动时指定 map YAML

仿真模式：

```bash
ros2 launch tourbot_bringup sim.launch.py \
  use_custom_sim:=true \
  custom_world:=/ws/install/tourbot_bringup/share/tourbot_bringup/worlds/<my_world>/world \
  custom_map:=/ws/install/tourbot_bringup/share/tourbot_bringup/maps/<my_map>/map_area.yaml
```

真机模式（`robot.launch.py`）目前 `map_yaml` 硬编码为 `cardboard_city`，要改 launch 文件或参数化。

---

## 3.调行为参数

### 3.1 对齐速度 / 容差

文件：`src/tourbot_behaviors/tourbot_behaviors/align_to_apriltag_server.py`

```python
SEARCH_ANGULAR_SPEED = 0.20    # tag 不可见时旋转搜索的角速度
ALIGN_KP            = 0.003    # 像素误差 → 角速度的比例增益
MAX_ANGULAR_SPEED   = 0.30     # 角速度上限
```

建议从 P 增益开始尝试：

- 抖动严重 → 减小 `ALIGN_KP`
- 收敛太慢 → 增大 `ALIGN_KP` 或 `MAX_ANGULAR_SPEED`
- 永远找不到 tag → 检查相机 topic 和 `x_tolerance_px`

### 3.2 门穿越参数

文件：`src/tourbot_behaviors/tourbot_behaviors/door_behavior_server.py`

```python
self.declare_parameter("backup_distance_default", 0.9)
self.declare_parameter("backup_speed_default",    0.15)
self.declare_parameter("wait_seconds_default",    3.0)
self.declare_parameter("forward_distance_default", 1.5)
self.declare_parameter("forward_speed_default",   0.18)
self.declare_parameter("control_rate_hz",         20.0)
```

注意：`tour_deliberation_node.run_door_sequence()` 把 goal 里这些字段都填 `0.0`，所以**实际生效的是这里的默认值**。想改全局默认，改这里即可。

---

## 4.写一个全新的行为 Server

下面以"在 landmark 处播一段语音"为例，演练一个最小行为 server。

### 4.1 定义 Action 接口

新文件：`src/tourbot_interfaces/action/SayAtLandmark.action`

```text
# Goal
string text
float32 timeout_sec
---
# Result
bool success
string message
---
# Feedback
string state
```

在 `src/tourbot_interfaces/CMakeLists.txt` 已有 action 文件列表里加上：

```cmake
"action/SayAtLandmark.action"
```

### 4.2 写 Server 节点

新文件：`src/tourbot_behaviors/tourbot_behaviors/say_server.py`

```python
import rclpy
from rclpy.action import ActionServer
from rclpy.node import Node
from tourbot_interfaces.action import SayAtLandmark


class SayServer(Node):
    def __init__(self):
        super().__init__("say_server")
        self._server = ActionServer(
            self,
            SayAtLandmark,
            "say_at_landmark",
            execute_callback=self.execute_cb,
        )
        self.get_logger().info("SayServer ready.")

    def execute_cb(self, goal_handle):
        text = goal_handle.request.text
        self.get_logger().info(f"[say] {text}")
        goal_handle.succeed()
        result = SayAtLandmark.Result()
        result.success = True
        result.message = "spoken"
        return result


def main():
    rclpy.init()
    rclpy.spin(SayServer())
    rclpy.shutdown()


if __name__ == "__main__":
    main()
```

### 4.3 注册 entry point

`src/tourbot_behaviors/setup.py` 的 `entry_points`：

```python
"say_server = tourbot_behaviors.say_server:main",
```

### 4.4 加入 mission launch

`src/tourbot_bringup/launch/mission.launch.py`：

```python
say_server = Node(
    package="tourbot_behaviors",
    executable="say_server",
    name="say_server",
)
# ...
TimerAction(period=3.5, actions=[say_server]),
```

### 4.5 在 mission 主循环中调用

`tour_deliberation_node.py`：

```python
from tourbot_interfaces.action import SayAtLandmark

say_client = ActionClient(navigator, SayAtLandmark, "say_at_landmark")

# 在每个 landmark 对齐完成后：
say_goal = SayAtLandmark.Goal()
say_goal.text = f"Welcome to {landmark['name']}"
say_goal.timeout_sec = 5.0
call_action_and_wait(navigator, say_client, say_goal)
```

### 4.6 构建并验证

```bash
docker compose -f docker_stuff/compose.yaml run --rm build
docker compose -f docker_stuff/compose.yaml run --rm --no-deps dev bash -lc '
  source install/setup.bash
  ros2 action list | grep say_at_landmark
  ros2 action send_goal /say_at_landmark \
    tourbot_interfaces/action/SayAtLandmark \
    "{text: hello, timeout_sec: 5.0}" --feedback
'
```

---

## 5.开发流程图

```mermaid
flowchart TB
    classDef edit fill:"#fef3c7",stroke:"#92400e"
    classDef build fill:"#dbeafe",stroke:"#1d4ed8"
    classDef run fill:"#dcfce7",stroke:"#15803d"
    classDef check fill:"#fce7f3",stroke:"#9d174d"

    A["编辑源码 src 下文件"]:::edit
    B["docker compose run --rm build"]:::build
    C{"构建成功？"}
    D["看 colcon 报错<br/>修语法 / 依赖"]:::edit
    E["重启目标服务<br/>--force-recreate"]:::run
    F["ros2 node list / topic / action<br/>确认接口出现"]:::check
    G{"接口正常？"}
    H["docker logs 看节点日志<br/>修参数 / 修订阅名"]:::edit
    I["ros2 action send_goal<br/>或 RViz Nav2 Goal 验证"]:::check
    J{"行为正确？"}
    K["调参数 / 改逻辑"]:::edit
    L["完成"]

    A --> B --> C
    C -->|"否"| D --> A
    C -->|"是"| E --> F --> G
    G -->|"否"| H --> A
    G -->|"是"| I --> J
    J -->|"否"| K --> A
    J -->|"是"| L
```

---

## 6.常见坑速查

| 现象 | 根因 | 排查与修复 |
|---|---|---|
| `colcon build` 找不到 action 头文件 | `tourbot_interfaces/CMakeLists.txt` 没加新 `.action` | 加上 → 重新 `build` |
| `ros2 action list` 看不到新 action | `setup.py` 没注册 entry point；或 mission launch 没加节点 | 都补上 → rebuild |
| `cmd_vel` 发了机器人不动 | 发成了 `Twist`，但 Nav2 期望 `TwistStamped` | 改为 `TwistStamped`，带 `header.stamp` |
| Nav2 一直 `inactive` | 没设初始位姿，或 lifecycle manager 没 activate | RViz 用 `2D Pose Estimate`；看 `nav2_post_localization_activator` 日志 |
| Gazebo GUI 黑屏 / 软渲染 | 没走 VirtualGL | 用 `vglrun -d :0 ros2 launch ...` 启动 |
| `apriltag_node` 收不到图 | remap 不对 | 检查 `apriltag_pipeline.launch.py` 里 `image_rect` / `camera_info` 的 remap |
| 改完 yaml 不生效 | 没重新 `colcon build`，share 目录没更新 | 任何 install 数据文件改了都得 rebuild |

---

## 7.推荐进阶路径

```text
Day 1-3 :   跑通 sim，能看到机器人巡游
Day 4-7 :   改 landmark 坐标，验证还能跑
Week 2  :   把 map_name 参数化
Week 3  :   写一个 say_server / led_server 类玩具行为
Week 4  :   阅读 align_to_apriltag_server 全源码，理解 ReentrantCallbackGroup
Month 2 :   补完 cardboard_city world，加 AprilTag 模型，跑完整自动 tour
Month 3 :   把 mission 改造成 behavior tree（py_trees_ros），代替线性循环
```

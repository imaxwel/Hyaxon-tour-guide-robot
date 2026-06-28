# 当前工程有没有使用行为树，以及它是怎么实现的

结论先说清楚：**当前工程有使用行为树，但不是项目自己手写的行为树。**

更准确地说：

- 导航层使用了 Nav2 的 `bt_navigator`，也就是 Nav2 内置的 Behavior Tree 执行器。
- 工程没有自定义 BehaviorTree.CPP v4 的 C++ BT 节点插件。
- 工程没有自定义 Nav2 BT XML 文件。
- 工程自己的导览任务逻辑不是行为树实现，而是一个 Python ROS 2 节点按顺序调用 Nav2 和自定义 action server。

所以这个项目是两层结构：

```text
项目任务层：Python 顺序逻辑
  tour_deliberation_node.py
  - 读取 landmarks.yaml
  - 计算参观顺序
  - 逐个导航到目标点
  - 调用对齐 AprilTag / 等待开门 / 穿门等 action

导航执行层：Nav2 内置行为树
  bt_navigator
  - 接收 NavigateToPose / NavigateThroughPoses action
  - 加载 Nav2 默认 BT XML
  - 周期性 tick 行为树
  - 调 planner / controller / recovery 等 Nav2 组件
```

---

## 1. 判断依据

### 1.1 明确启用了 Nav2 的 `bt_navigator`

文件：`src/tourbot_bringup/config/nav2_params.yaml`

关键配置在第 47 行附近：

```yaml
bt_navigator:
  ros__parameters:
    enable_stamped_cmd_vel: true
    global_frame: map
    robot_base_frame: base_link
    odom_topic: /odom
    bt_loop_duration: 10
    default_server_timeout: 20
    wait_for_service_timeout: 1000
    action_server_result_timeout: 900.0
    navigators: ["navigate_to_pose", "navigate_through_poses"]
    navigate_to_pose:
      plugin: "nav2_bt_navigator::NavigateToPoseNavigator"
    navigate_through_poses:
      plugin: "nav2_bt_navigator::NavigateThroughPosesNavigator"
```

这说明 Nav2 会启动 `bt_navigator` 节点，并加载两个 navigator 插件：

- `nav2_bt_navigator::NavigateToPoseNavigator`
- `nav2_bt_navigator::NavigateThroughPosesNavigator`

它们分别处理：

- 单目标点导航：`NavigateToPose`
- 多目标点导航：`NavigateThroughPoses`

这两个 navigator 内部都是基于 Nav2 行为树执行导航逻辑。

### 1.2 没有配置项目自定义 BT XML，使用 Nav2 默认树

同一个文件里有这段注释：

```yaml
# 'default_nav_through_poses_bt_xml' and 'default_nav_to_pose_bt_xml' are use defaults:
# nav2_bt_navigator/navigate_to_pose_w_replanning_and_recovery.xml
# nav2_bt_navigator/navigate_through_poses_w_replanning_and_recovery.xml
```

这说明当前工程没有显式指定：

- `default_nav_to_pose_bt_xml`
- `default_nav_through_poses_bt_xml`

因此 Nav2 会使用默认 XML：

- `nav2_bt_navigator/navigate_to_pose_w_replanning_and_recovery.xml`
- `nav2_bt_navigator/navigate_through_poses_w_replanning_and_recovery.xml`

这些 XML 不在当前工程目录里，而是在安装好的 Nav2 包里。

### 1.3 没有加载自定义 BT 插件库

同一段配置里还有：

```yaml
# plugin_lib_names is used to add custom BT plugins to the executor (vector of strings).
# Built-in plugins are added automatically
# plugin_lib_names: []
```

这里 `plugin_lib_names` 是注释状态，没有真正启用。也就是说：

- 当前工程没有把自己的 BT 插件动态库加载进 Nav2 BT executor。
- 当前工程只依赖 Nav2 已经内置的 BT 节点。

### 1.4 启动文件确实把这个参数文件传给了 Nav2

文件：`src/tourbot_bringup/launch/robot.launch.py`

关键逻辑：

```python
nav2_params = os.path.join(
    get_package_share_directory('tourbot_bringup'),
    'config',
    'nav2_params.yaml'
)

nav2_launch = IncludeLaunchDescription(
    PythonLaunchDescriptionSource(
        os.path.join(
            get_package_share_directory('turtlebot4_navigation'),
            'launch',
            'nav2.launch.py'
        )
    ),
    launch_arguments={
        'params_file': nav2_params,
    }.items()
)
```

也就是：

```text
robot.launch.py
  -> turtlebot4_navigation/launch/nav2.launch.py
       -> 使用 tourbot_bringup/config/nav2_params.yaml
            -> 启用 bt_navigator
```

所以行为树不是“没用上”，而是藏在 Nav2 导航栈内部。

### 1.5 搜索结果没有发现自定义 BT 代码

在当前工程里搜索这些关键词：

```bash
rg -n "BehaviorTree|behaviortree|BT::|bt_xml|behavior_tree|nav2_bt|bt_navigator|BTCPP|BehaviorTree.CPP"
```

结果只有 `nav2_params.yaml` 里的 `bt_navigator` 配置。没有发现：

- `BT::SyncActionNode`
- `BT::StatefulActionNode`
- `BT::ConditionNode`
- `behaviortree_cpp`
- 自定义 `.xml` 行为树文件
- 自定义 Nav2 BT plugin 动态库配置

这进一步说明：**项目没有自己实现 BT.CPP v4 行为树，只有 Nav2 默认行为树在导航层工作。**

---

## 2. 对 BT.CPP v4 初学者：什么是行为树

行为树可以理解成一个“每隔一小段时间重新评估一次的任务决策树”。

在 BehaviorTree.CPP v4 里，树由很多节点组成。每次执行器 tick 根节点时，tick 会沿着树向下传播。每个节点返回三种状态之一：

```text
SUCCESS：这个节点完成并成功了
FAILURE：这个节点完成但失败了
RUNNING：这个节点还没完成，下次继续 tick
```

这三个状态是理解 BT 的核心。

### 2.1 叶子节点

叶子节点是真正做事或判断条件的节点。

常见叶子节点有两类：

```text
Action 节点
  做一件事。
  例如：计算路径、跟随路径、清理 costmap、旋转、等待。

Condition 节点
  判断一件事是否成立。
  例如：目标是否已到达、路径是否有效、错误码是否适合恢复。
```

在机器人里，Action 节点经常不是自己直接控制全部逻辑，而是封装一个 ROS 2 action、service 或 topic。

例如 Nav2 里的 `ComputePathToPose` BT 节点通常会调用 planner server，`FollowPath` BT 节点通常会调用 controller server。

### 2.2 控制节点

控制节点决定子节点的执行顺序。

最常见的是：

```text
Sequence
  从左到右 tick 子节点。
  只要有一个子节点 FAILURE，整个 Sequence 就 FAILURE。
  所有子节点 SUCCESS，整个 Sequence 才 SUCCESS。
  遇到 RUNNING，就返回 RUNNING，下次继续。

Fallback
  也叫 Selector。
  从左到右尝试子节点。
  只要有一个子节点 SUCCESS，整个 Fallback 就 SUCCESS。
  所有子节点 FAILURE，整个 Fallback 才 FAILURE。
  遇到 RUNNING，就返回 RUNNING。

Parallel
  同时 tick 多个子节点，按配置判断整体成功或失败。

ReactiveSequence / ReactiveFallback
  每次 tick 时会更积极地重新检查前面的条件。
  适合“如果条件变化，马上切换行为”的场景。
```

### 2.3 Decorator 节点

Decorator 节点包住一个子节点，改变它的行为。

典型例子：

```text
RateController
  控制子节点执行频率。
  例如规划路径不需要每 10ms 都重新规划，可以 1Hz 重规划。

RetryUntilSuccessful
  失败后重试。

Timeout
  超过时间就失败。

Inverter
  把 SUCCESS 变成 FAILURE，把 FAILURE 变成 SUCCESS。
```

Nav2 的默认树里经常用 decorator 控制重规划频率、恢复次数、超时等。

### 2.4 Blackboard 和 Ports

BT.CPP v4 里，节点之间通常通过 blackboard 传递数据。

可以把 blackboard 理解成树执行期间共享的一张键值表。

例如：

```xml
<ComputePathToPose goal="{goal}" path="{path}" />
<FollowPath path="{path}" />
```

这里：

- `{goal}` 是目标点。
- `ComputePathToPose` 从 blackboard 读取 `{goal}`。
- `ComputePathToPose` 计算出路径后写入 `{path}`。
- `FollowPath` 再从 blackboard 读取 `{path}` 去控制机器人跟踪路径。

在 BT.CPP v4 里，节点声明 input/output ports，树 XML 里把端口接到 blackboard 变量上。

---

## 3. Nav2 的行为树在本项目里怎么运行

### 3.1 启动链路

当前项目的导航启动链路是：

```text
ros2 launch tourbot_bringup robot.launch.py
  -> 启动 localization
  -> 延迟 5 秒启动 turtlebot4_navigation/nav2.launch.py
  -> nav2.launch.py 读取 tourbot_bringup/config/nav2_params.yaml
  -> Nav2 启动 bt_navigator
  -> bt_navigator 使用默认 BT XML
```

`bt_navigator` 是 Nav2 的一个 lifecycle node。它对外提供导航 action server，例如：

```text
/navigate_to_pose
/navigate_through_poses
```

当外部节点发送导航目标时，`bt_navigator` 会：

1. 接收目标点。
2. 把目标写入 BT blackboard。
3. 加载或复用导航行为树。
4. 按 `bt_loop_duration` 周期 tick 行为树。
5. 树里的 BT 节点去调用 planner、controller、costmap、recovery 等 Nav2 server。
6. 最终返回导航 action 的成功、失败或取消。

### 3.2 `bt_loop_duration: 10`

当前配置：

```yaml
bt_loop_duration: 10
```

在 Nav2 里这通常表示 BT 主循环 tick 周期，单位是毫秒。也就是大约每 10ms tick 一次根节点。

这不是说每 10ms 都重新全局规划一次。因为默认树里通常还有 `RateController` 等 decorator，用来限制某些昂贵行为的频率。例如全局规划可能以较低频率重算，而控制器跟踪路径可以持续运行。

### 3.3 `NavigateToPoseNavigator`

当前配置：

```yaml
navigators: ["navigate_to_pose", "navigate_through_poses"]
navigate_to_pose:
  plugin: "nav2_bt_navigator::NavigateToPoseNavigator"
```

这说明单点导航由 `NavigateToPoseNavigator` 处理。

项目任务层调用的是：

```python
navigator.startToPose(goal_pose)
```

位置：`src/tourbot_mission/tourbot_mission/tour_deliberation_node.py`

这会通过 TurtleBot4 的导航封装向 Nav2 发导航目标。Nav2 收到目标后，内部使用 `bt_navigator` 的行为树执行导航。

### 3.4 默认 `navigate_to_pose` 树大概做什么

当前工程没有保存这份 XML，所以不要把下面当成当前仓库里的源码。它是对 Nav2 默认树的简化解释。

Nav2 默认 `navigate_to_pose_w_replanning_and_recovery.xml` 的核心思想大致是：

```text
NavigateRecovery
  PipelineSequence: 正常导航主流程
    RateController: 控制重规划频率
      ComputePathToPose: 从当前位置到目标点规划全局路径
        如果规划失败，尝试清理 global costmap 后重试

    FollowPath: 控制机器人沿路径运动
      如果控制失败，尝试清理 local costmap 后重试

  Recovery 行为: 如果主流程失败，执行恢复动作
    清理 costmap
    旋转或等待
    重新尝试导航
```

可以把它理解为：

```text
先规划路径
再跟踪路径
中途周期性重规划
失败时做局部/全局恢复
恢复后再试
重试耗尽则整个导航失败
```

这就是 Nav2 行为树最常见的价值：导航不是单纯“调用 planner 一次，再调用 controller 一次”，而是把“规划、控制、重规划、检测错误、恢复、重试”组合成一个可以持续 tick 的树。

### 3.5 `NavigateThroughPosesNavigator`

当前也启用了：

```yaml
navigate_through_poses:
  plugin: "nav2_bt_navigator::NavigateThroughPosesNavigator"
```

这个 navigator 用于多目标点导航，对应 Nav2 的 `NavigateThroughPoses` action。

但是当前任务层代码并没有明显直接使用 `NavigateThroughPoses` 来一次性发多个路点。它是在 Python 里自己循环每个 landmark：

```python
for landmark in goal_landmarks:
    goal_pose = landmark_to_pose(navigator, landmark)
    navigator.startToPose(goal_pose)
```

所以当前导览顺序不是由 Nav2 多路点 BT 决定的，而是由 `tour_deliberation_node.py` 的 Python 循环决定的。

---

## 4. 项目自己的任务层不是行为树

### 4.1 任务节点在哪里

文件：

```text
src/tourbot_mission/tourbot_mission/tour_deliberation_node.py
```

它的主流程在 `main()` 里。

这个节点做了几件事：

1. 创建 `TurtleBot4Navigator`。
2. 创建三个自定义 action client：
   - `AlignToAprilTag`
   - `WaitForTagRemoved`
   - `DoorTraverse`
3. 从 YAML 加载 landmark。
4. 设置初始位姿。
5. 等待 Nav2 active。
6. 用最近邻贪心策略计算参观顺序。
7. 对每个 landmark 执行导航和交互动作。

这是一段普通命令式 Python 逻辑，不是 BT XML，也不是 BT.CPP v4。

### 4.2 任务层的顺序逻辑

代码整体可以简化成：

```text
初始化 ROS
创建 TurtleBot4Navigator
创建 action clients
读取 landmarks
设置 initial pose
等待 Nav2 active

按最近邻策略排序 landmarks
把 home 加到最后

for 每个 landmark:
  1. navigator.startToPose(goal_pose)
  2. 对齐该 landmark 的 AprilTag
  3. 如果 tag_id 是 1 或 2，认为是门：
       等待 tag 消失
       执行穿门动作
  4. 如果不是门：
       原地转 180 度朝外
  5. 等待 5 秒

任务结束
```

对应代码：

```python
for landmark in goal_landmarks:
    goal_pose = landmark_to_pose(navigator, landmark)
    navigator.startToPose(goal_pose)

    time.sleep(1.5)

    tag_id = int(landmark["tag_id"])

    align_goal = AlignToAprilTag.Goal()
    align_goal.tag_id = tag_id
    align_goal.timeout_sec = 30.0
    align_goal.x_tolerance_px = 7.0

    aligned = call_action_and_wait(
        navigator,
        align_client,
        align_goal
    )

    if not aligned:
        continue

    if is_door_tag(tag_id):
        door_ok = run_door_sequence(...)
        if not door_ok:
            continue

    if not is_door_tag(tag_id):
        rotated_pose = landmark_to_rotated_pose(navigator, landmark)
        navigator.startToPose(rotated_pose)
```

如果从 BT 的角度看，它有点像一个手写的固定流程：

```text
Sequence
  LoadLandmarks
  SetInitialPose
  WaitNav2Active
  PlanTourOrder
  ForEachLandmark
    NavigateToLandmark
    AlignToAprilTag
    Fallback / IfThenElse
      DoorSequence
      RotateAwayFromLandmark
```

但这只是“可以这样理解”，当前代码并没有把它实现成行为树。

---

## 5. 自定义 behavior action server 是什么

当前工程有一个包叫：

```text
src/tourbot_behaviors
```

这个名字里有 `behaviors`，但它不等于 Behavior Tree。

这里的 behavior 指的是 ROS 2 action server 形式的机器人行为。它们是任务节点可以调用的能力模块。

启动文件：

```text
src/tourbot_bringup/launch/mission.launch.py
```

会启动：

```text
apriltag_pipeline
align_to_apriltag_server
wait_for_tag_removed_server
door_behavior_server
tour_deliberation_node
```

这些 action server 不是 BT.CPP 插件。它们是普通 Python ROS 2 节点。

### 5.1 `align_to_apriltag_server`

文件：

```text
src/tourbot_behaviors/tourbot_behaviors/align_to_apriltag_server.py
```

它实现的 action：

```text
src/tourbot_interfaces/action/AlignToAprilTag.action
```

接口：

```text
Goal:
  int32 tag_id
  float32 timeout_sec
  float32 x_tolerance_px

Result:
  bool success
  string message

Feedback:
  float32 x_error_px
  bool tag_visible
  string state
```

这个 server 的逻辑：

1. 订阅 AprilTag 检测结果 `/detections`。
2. 订阅相机信息 `/oakd/rgb/preview/camera_info`，拿到图像宽度。
3. 发布 `/cmd_vel` 控制机器人原地转。
4. 收到 action goal 后，寻找指定 `tag_id`。
5. 如果还没有 camera info，则停止并反馈 `waiting_for_camera_info`。
6. 如果没看到 tag，则按固定角速度旋转搜索，反馈 `searching_for_tag`。
7. 如果看到 tag，则计算 tag 中心和图像中心的横向像素误差。
8. 如果误差小于 `x_tolerance_px`，停止机器人并返回成功。
9. 否则按比例控制角速度继续对齐。
10. 超时或取消则返回失败。

简化伪代码：

```text
while ROS ok:
  if canceled:
    stop
    return failure

  if timeout:
    stop
    return failure

  if no camera info:
    stop
    feedback waiting_for_camera_info
    continue

  detection = find tag_id

  if detection not found:
    rotate with SEARCH_ANGULAR_SPEED
    feedback searching_for_tag
    continue

  x_error = tag_center_x - image_center_x

  if abs(x_error) <= tolerance:
    stop
    return success

  angular_z = clamp(-ALIGN_KP * x_error)
  publish angular_z
  feedback aligning
```

从 BT 初学者角度看，这个 action server 很像一个可以封装成 BT Action 节点的能力：

```xml
<AlignToAprilTag tag_id="{tag_id}" timeout_sec="30.0" x_tolerance_px="7.0" />
```

但当前项目没有这个 BT 节点。当前是 Python 任务节点直接调用这个 ROS 2 action。

### 5.2 `wait_for_tag_removed_server`

文件：

```text
src/tourbot_behaviors/tourbot_behaviors/wait_for_tag_removed_server.py
```

它实现的 action：

```text
src/tourbot_interfaces/action/WaitForTagRemoved.action
```

接口：

```text
Goal:
  int32 tag_id
  float32 timeout_sec
  float32 missing_duration_sec

Result:
  bool success
  string message

Feedback:
  bool tag_visible
  float32 missing_time_sec
  string state
```

这个 server 的逻辑：

1. 订阅 `/detections`。
2. 收到目标后检查指定 `tag_id` 是否仍然可见。
3. 如果 tag 可见，重置 missing timer。
4. 如果 tag 不可见，开始累计不可见时长。
5. 不可见时长达到 `missing_duration_sec` 后成功。
6. 超过 `timeout_sec` 仍未满足则失败。

项目用它来表示门状态：

```text
tag 可见   -> 门还没打开
tag 不可见 -> 认为门已经打开或 tag 已被移出视野
```

这个设计是简化过的，不是真正的门状态识别。

从 BT 角度看，它也可以被封装成一个 Action 节点：

```xml
<WaitForTagRemoved tag_id="{door_tag_id}" timeout_sec="60.0" missing_duration_sec="3.0" />
```

但当前没有这样做。

### 5.3 `door_behavior_server`

文件：

```text
src/tourbot_behaviors/tourbot_behaviors/door_behavior_server.py
```

它实现的 action：

```text
src/tourbot_interfaces/action/DoorTraverse.action
```

接口：

```text
Goal:
  int32 tag_id
  float32 backup_distance
  float32 backup_speed
  float32 wait_seconds
  float32 forward_distance
  float32 forward_speed

Result:
  bool success
  string message

Feedback:
  string current_state
  float32 distance_traveled
```

这个 server 控制门通行行为。

它订阅：

```text
/odom
```

发布：

```text
/cmd_vel
```

它根据 `tag_id` 区分门类型：

```text
tag_id == 1:
  OUTWARD，向外开的门
  不后退，等待后直接向前通过

tag_id == 2:
  INWARD，向内开的门
  先转身、远离门后退一段距离、再转回来、等待、再向前通过
```

注意这里的“后退”实际实现方式不是直接给负速度，而是：

```text
转 180 度
向前开一段距离，效果上远离门
再转 180 度面向门
```

穿门动作简化后是：

```text
如果是 inward door:
  turn_relative_angle(pi)
  drive_linear_distance(backup_distance)
  turn_relative_angle(pi)

wait(wait_seconds)

drive_linear_distance(forward_distance)
return success
```

这也是普通 action server，不是 BT 节点。

---

## 6. 当前完整运行流程

把 Nav2 BT 和项目 Python 任务层合在一起看，实际运行流程大致是：

```text
1. 启动 robot.launch.py
   - localization
   - Nav2
   - bt_navigator
   - RViz

2. 启动 mission.launch.py
   - AprilTag perception
   - align_to_apriltag_server
   - wait_for_tag_removed_server
   - door_behavior_server
   - tour_deliberation_node

3. tour_deliberation_node 初始化
   - 创建 TurtleBot4Navigator
   - 创建自定义 action clients
   - 读取 cardboard_city landmarks
   - 设置 initial pose
   - 等待 Nav2 active

4. tour_deliberation_node 计算参观顺序
   - 当前使用最近邻贪心
   - 最后追加 home

5. 对每个 landmark
   - 发送 NavigateToPose 给 Nav2
       -> Nav2 bt_navigator 执行默认行为树
       -> planner/controller/recovery 由 BT 调度

   - 调用 AlignToAprilTag action
       -> Python action server 旋转机器人对齐 tag

   - 如果 tag 是门 tag
       -> 调用 WaitForTagRemoved action
       -> 调用 DoorTraverse action

   - 如果不是门 tag
       -> 调用 Nav2 去旋转到反向 pose

6. 所有点完成后任务结束
```

这里要特别分清：

```text
NavigateToPose 内部：Nav2 BT
AlignToAprilTag：不是 BT，是 Python action server
WaitForTagRemoved：不是 BT，是 Python action server
DoorTraverse：不是 BT，是 Python action server
导览顺序选择：不是 BT，是 Python 贪心算法 + for 循环
```

---

## 7. 为什么容易误以为整个项目都是行为树

这个工程里有几个名字容易混淆：

```text
tourbot_behaviors
behavior server
bt_navigator
Nav2 behavior tree
```

它们不是一回事。

### 7.1 `tourbot_behaviors` 不是 BehaviorTree.CPP

`tourbot_behaviors` 是项目自定义机器人行为包。里面的行为以 ROS 2 action server 形式实现。

它们可以被任务节点调用，也可以将来被 BT 节点调用。但目前它们本身不是 BT 插件。

### 7.2 `bt_navigator` 才是行为树执行器

`bt_navigator` 是 Nav2 的组件，内部使用 BehaviorTree.CPP。

它做的是导航任务的行为树，不负责整个导览任务的高层决策。

### 7.3 Nav2 的默认树不在当前仓库里

当前仓库没有：

```text
navigate_to_pose_w_replanning_and_recovery.xml
navigate_through_poses_w_replanning_and_recovery.xml
```

它们在 Nav2 安装包里。

如果要查看实际 XML，可以在 ROS 2 环境里找：

```bash
ros2 pkg prefix nav2_bt_navigator
```

然后到对应 share 目录下查找 XML：

```bash
find $(ros2 pkg prefix nav2_bt_navigator)/share/nav2_bt_navigator -name "*.xml"
```

---

## 8. 如果要把项目高层任务改成真正的 BT，可以怎么做

当前项目并没有这么做，但它已经有一些适合 BT 化的模块。

### 8.1 可以保留现有 action server

已有这些 ROS 2 action：

```text
AlignToAprilTag
WaitForTagRemoved
DoorTraverse
```

这些很适合被 BT Action 节点调用。因为 BT action 节点通常应该是“发起一个异步任务，然后持续返回 RUNNING，直到 action result 回来再返回 SUCCESS/FAILURE”。

例如未来可以有：

```xml
<Sequence name="VisitLandmark">
  <NavigateToPose goal="{landmark_pose}" />
  <AlignToAprilTag tag_id="{tag_id}" timeout_sec="30.0" x_tolerance_px="7.0" />
  <Fallback>
    <Sequence name="DoorCase">
      <IsDoorTag tag_id="{tag_id}" />
      <WaitForTagRemoved tag_id="{tag_id}" timeout_sec="60.0" missing_duration_sec="3.0" />
      <DoorTraverse tag_id="{tag_id}" />
    </Sequence>
    <RotateAwayFromLandmark pose="{rotated_pose}" />
  </Fallback>
</Sequence>
```

这只是示意，不是当前仓库里已有的 XML。

### 8.2 需要 C++ BT 插件或可用的通用 action BT 节点

Nav2 的 BT 节点是 BehaviorTree.CPP 插件。典型方式是：

1. 新建 C++ 包。
2. 写继承 Nav2 BT action node 基类或 BT.CPP node 基类的插件。
3. 在插件中创建 ROS 2 action client，调用现有 Python action server。
4. 编译成动态库。
5. 在 `nav2_params.yaml` 的 `plugin_lib_names` 中加载这个动态库。
6. 写自定义 BT XML，把新节点放进树里。
7. 设置 `default_nav_to_pose_bt_xml` 或新的 navigator 参数，让 Nav2 加载你的树。

也就是说，现有 Python action server 可以继续用；但要让 Nav2 BT 直接调用它们，需要有 BT 插件作为“桥”。

### 8.3 另一条路线：单独做一个任务级 BT executor

也可以不把导览任务塞进 Nav2 的 `bt_navigator`，而是单独做一个 mission-level BT：

```text
Mission BT executor
  - VisitLandmark
  - AlignToAprilTag
  - DoorSequence
  - RotateAway

Nav2 bt_navigator
  - 只负责 NavigateToPose 内部导航树
```

这种架构更清晰：

```text
任务级 BT：决定现在该去哪个 landmark，该执行哪个交互
导航级 BT：Nav2 内部负责如何安全到达目标点
```

缺点是要维护两个 BT 层次；优点是职责分明，导览逻辑不会和 Nav2 默认导航树强耦合。

---

## 9. 当前项目用行为树的边界总结

### 使用了行为树的部分

```text
Nav2 bt_navigator
  - NavigateToPose
  - NavigateThroughPoses
  - 默认 BT XML
  - planner/controller/recovery 调度
```

证据：

```text
src/tourbot_bringup/config/nav2_params.yaml
  bt_navigator:
  navigators: ["navigate_to_pose", "navigate_through_poses"]
  plugin: "nav2_bt_navigator::NavigateToPoseNavigator"
  plugin: "nav2_bt_navigator::NavigateThroughPosesNavigator"
```

### 没有使用自定义行为树的部分

```text
tourbot_mission/tour_deliberation_node.py
  - 任务编排是 Python for 循环和 if 判断

tourbot_behaviors/*.py
  - 是 ROS 2 action server
  - 不是 BT.CPP 插件

当前仓库
  - 没有自定义 BT XML
  - 没有 BT.CPP C++ 节点
  - 没有 plugin_lib_names 加载自定义 BT 库
```

### 一句话总结

**这个工程当前是“任务层顺序编排 + Nav2 内部行为树导航”的结构，而不是“整个导览任务都由项目自定义行为树驱动”的结构。**

---

## 10. 给 BT4 初学者的阅读顺序

如果你是刚接触 BehaviorTree.CPP v4，可以按这个顺序看当前项目：

### 第一步：看 Nav2 BT 是怎么被打开的

看：

```text
src/tourbot_bringup/config/nav2_params.yaml
```

重点看：

```yaml
bt_navigator:
  ros__parameters:
    navigators: ["navigate_to_pose", "navigate_through_poses"]
    navigate_to_pose:
      plugin: "nav2_bt_navigator::NavigateToPoseNavigator"
```

你要理解：这里只是配置 Nav2 的 BT navigator，不是写树本身。

### 第二步：看任务层怎么触发 Nav2 BT

看：

```text
src/tourbot_mission/tourbot_mission/tour_deliberation_node.py
```

重点看：

```python
navigator.startToPose(goal_pose)
```

这一步会向 Nav2 发导航目标。真正的路径规划、路径跟踪、恢复行为，由 Nav2 的 BT navigator 内部处理。

### 第三步：看项目自己的动作能力

看：

```text
src/tourbot_behaviors/tourbot_behaviors/align_to_apriltag_server.py
src/tourbot_behaviors/tourbot_behaviors/wait_for_tag_removed_server.py
src/tourbot_behaviors/tourbot_behaviors/door_behavior_server.py
```

这些不是 BT 节点，但它们是未来做任务级 BT 时很适合包装的 leaf action。

### 第四步：去 Nav2 安装包里看默认 XML

当前工程没有默认 XML 的内容。要看实际树结构，需要在装好 ROS 2/Nav2 的环境中查 Nav2 包：

```bash
find $(ros2 pkg prefix nav2_bt_navigator)/share/nav2_bt_navigator -name "*.xml"
```

然后重点看：

```text
navigate_to_pose_w_replanning_and_recovery.xml
navigate_through_poses_w_replanning_and_recovery.xml
```

看 XML 时重点关注这些节点：

```text
RecoveryNode
PipelineSequence
RateController
ComputePathToPose
FollowPath
ClearEntireCostmap
```

这些就是 Nav2 默认导航 BT 的骨架。

---

## 11. 当前架构的优点和限制

### 优点

```text
1. 简单直观
   Python 任务层容易读，容易调试。

2. 充分复用 Nav2
   导航复杂性由 Nav2 默认 BT 处理，不需要项目自己重写 planner/controller/recovery 调度。

3. 自定义行为边界清楚
   AprilTag 对齐、等待开门、穿门都做成独立 action server。

4. 未来容易 BT 化
   已有 action server 可以继续作为能力模块，只需要新增 BT action 节点包装。
```

### 限制

```text
1. 高层任务不可视化
   由于导览逻辑不是 BT XML，不能直接用 Groot 这类 BT 工具查看完整任务树。

2. 高层恢复策略较弱
   Python 中的失败处理主要是 continue 或返回 False，不像 BT 可以清晰表达重试、fallback、局部恢复。

3. 行为组合不够声明式
   新增任务分支时要改 Python 控制流，而不是改 XML 树。

4. Nav2 默认 BT 只管导航
   它不知道 landmark、door、AprilTag 对齐这些项目级语义。
```

---

## 12. 最终判断

当前工程确实使用了行为树，但只是在 Nav2 导航层使用。

具体实现方式是：

```text
robot.launch.py
  -> 启动 TurtleBot4 Nav2
  -> 使用 nav2_params.yaml
  -> 配置 bt_navigator
  -> bt_navigator 使用 Nav2 默认导航 BT XML
  -> 任务节点调用 TurtleBot4Navigator.startToPose()
  -> Nav2 BT 执行规划、控制、恢复
```

项目自己的导览流程是：

```text
tour_deliberation_node.py
  -> Python 顺序逻辑
  -> 调 Nav2 导航
  -> 调自定义 ROS 2 action server
  -> 根据 tag_id 判断是否执行门序列
```

项目自己的自定义行为是：

```text
align_to_apriltag_server.py
wait_for_tag_removed_server.py
door_behavior_server.py
```

它们目前是 ROS 2 action server，不是 BehaviorTree.CPP v4 插件。

所以最准确的一句话是：

```text
本项目使用了 Nav2 默认行为树来完成导航，但没有实现项目自定义的 BT.CPP v4 行为树；导览任务编排目前由 Python 节点顺序控制。
```

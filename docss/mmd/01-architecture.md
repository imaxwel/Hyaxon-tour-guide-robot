# 01 软件架构图：代码层模块组织

> 适用对象：1-3 个月初学者
> 目标：看完本篇，能在仓库里 **快速定位** 每个功能在哪个包、哪个文件。

---

## 1.先看一眼总览

本工程是一个标准 ROS 2 工作空间，`src/` 下含 9 个包，分两类：

- **第三方包**：`apriltag`、`apriltag_msgs`、`apriltag_ros`（视觉 tag 检测）
- **工程自研包**：`tourbot_*` 系列 6 个，承担"机器人导游"的业务逻辑

下面的 Mermaid 图把这 9 个包按 **职责层** 摆好，并用 **背景色** 区分层级。

```mermaid
%% 工程整体软件模块结构图
graph TB
    classDef appLayer fill:"#fde68a",stroke:"#92400e",color:"#1f2937"
    classDef behaviorLayer fill:"#bbf7d0",stroke:"#166534",color:"#1f2937"
    classDef perceptionLayer fill:"#bfdbfe",stroke:"#1e3a8a",color:"#1f2937"
    classDef interfaceLayer fill:"#e9d5ff",stroke:"#5b21b6",color:"#1f2937"
    classDef configLayer fill:"#fecaca",stroke:"#991b1b",color:"#1f2937"
    classDef bringupLayer fill:"#cffafe",stroke:"#155e75",color:"#1f2937"
    classDef thirdparty fill:"#e5e7eb",stroke:"#374151",color:"#1f2937"

    subgraph APP["应用层 【任务策略】"]
        A1["tourbot_mission<br/>tour_deliberation_node"]
    end

    subgraph BEH["行为层 【动作服务器】"]
        B1["align_to_apriltag_server<br/>视觉对齐"]
        B2["wait_for_tag_removed_server<br/>等门开"]
        B3["door_behavior_server<br/>门穿越"]
    end

    subgraph PER["感知层 【视觉处理】"]
        P1["apriltag_pipeline.launch<br/>tag 检测流水线"]
        P2["apriltag_ros<br/>第三方 tag 节点"]
    end

    subgraph IFC["接口层 【自定义消息】"]
        I1["tourbot_interfaces<br/>AlignToAprilTag<br/>WaitForTagRemoved<br/>DoorTraverse"]
    end

    subgraph CFG["配置层 【地标数据】"]
        C1["tourbot_landmarks<br/>landmarks.yaml<br/>landmarks_loader"]
    end

    subgraph BRG["启动层 【launch 编排】"]
        L1["tourbot_bringup<br/>sim.launch.py<br/>robot.launch.py<br/>mission.launch.py"]
        L2["maps / worlds<br/>nav2_params.yaml"]
    end

    subgraph TP["第三方层"]
        T1["apriltag<br/>核心算法"]
        T2["apriltag_msgs<br/>消息定义"]
        T3["Nav2 / TurtleBot4<br/>来自上游 apt 包"]
    end

    A1 -->|"调用 action"| B1
    A1 -->|"调用 action"| B2
    A1 -->|"调用 action"| B3
    A1 -->|"读取"| C1
    A1 -->|"调用 NavigateToPose"| T3

    B1 -->|"订阅 /detections"| P1
    B2 -->|"订阅 /detections"| P1

    P1 --> P2
    P2 --> T1
    P2 --> T2

    B1 -->|"使用 action 定义"| I1
    B2 -->|"使用 action 定义"| I1
    B3 -->|"使用 action 定义"| I1
    A1 -->|"使用 action 定义"| I1

    L1 -->|"启动"| A1
    L1 -->|"启动"| B1
    L1 -->|"启动"| B2
    L1 -->|"启动"| B3
    L1 -->|"启动"| P1
    L1 -->|"启动"| T3
    L1 -->|"加载"| L2

    class A1 appLayer
    class B1,B2,B3 behaviorLayer
    class P1,P2 perceptionLayer
    class I1 interfaceLayer
    class C1 configLayer
    class L1,L2 bringupLayer
    class T1,T2,T3 thirdparty
```

**怎么看这张图**：

- 箭头方向 = "谁依赖谁"。`tour_deliberation_node` 是大脑，它依赖下面 3 个行为 server。
- 同色块 = 同一层职责。改地标颜色不会影响算法层。
- 第三方层独立，不要去改它的代码，只在配置里调。

---

## 2.每个包都做啥？

### 2.1 `tourbot_bringup` 启动层

**职责**：把一堆节点串成一条命令就能起的整体。它本身没多少业务代码，主要是 launch 文件 + 配置。

```text
tourbot_bringup/
├── launch/
│   ├── sim.launch.py        ← 仿真总开关
│   ├── robot.launch.py      ← 真机/导航栈
│   └── mission.launch.py    ← 任务 + 感知 + 行为
├── config/
│   └── nav2_params.yaml     ← Nav2 调参，含 enable_stamped_cmd_vel: true
├── maps/
│   └── cardboard_city/      ← 占用栅格地图（.pgm + .yaml）
├── worlds/
│   └── cardboard_city/      ← Gazebo 世界（.sdf）
└── tourbot_bringup/
    ├── odom_tf_compat.py                   ← 把 /odom 重新发布为 TF
    └── nav2_post_localization_activator.py ← AMCL 出 TF 后激活 Nav2 lifecycle
```

**初学者要点**：`odom_tf_compat` 和 `nav2_post_localization_activator` 是为了让 Nav2 仿真链路顺起来而加的"胶水"节点，名字怪不要紧。

---

### 2.2 `tourbot_mission` 应用层

**职责**：整个 tour 的"剧本"，按顺序去 landmark、对齐、过门、回家。

```text
tourbot_mission/
└── tourbot_mission/
    └── tour_deliberation_node.py    ← 唯一可执行节点
```

**关键逻辑**（不用记代码，记规则）：

```text
1. 加载 landmarks.yaml
2. 设置初始位姿 = home（连发 10 次）
3. 等 Nav2 active
4. 用 "最近邻贪心" 给 landmarks 排序
5. 对每个 landmark：
   a. Nav2 startToPose 走过去
   b. /align_to_apriltag 对齐 tag
   c. 如果 tag_id ∈ {1, 2} → 门流程
   d. 否则 → 原地转 180 度
6. 回 home，结束
```

**门规则硬编码在代码里**：

```python
def is_door_tag(tag_id: int) -> bool:
    return tag_id in (1, 2)
```

要加更多门 tag，要么改这函数，要么把它读 YAML，参考 [05-dev-guide.md](./05-dev-guide.md)。

---

### 2.3 `tourbot_behaviors` 行为层

**职责**：把"对齐 / 等门 / 穿门"这三件具体动作做成 **action server**，让大脑可以"叫外卖式"调用。

```text
tourbot_behaviors/
├── tourbot_behaviors/
│   ├── align_to_apriltag_server.py       ← action /align_to_apriltag
│   ├── wait_for_tag_removed_server.py    ← action /wait_for_tag_removed
│   ├── door_behavior_server.py           ← action /door_traverse
│   ├── landmark_task_server.py           ← 占位，未实现
│   └── door_detector_node.py             ← 已废弃，不用看
└── launch/
    ├── align_to_apriltag.launch.py
    └── door_behavior.launch.py           ← 引用了缺失节点，不要直接用
```

#### 三个行为各自的核心算法

| 行为 | 输入 | 输出 | 算法核心 |
|---|---|---|---|
| **align_to_apriltag** | `/detections`、`/camera_info` | `/cmd_vel` | 比例控制：`ω = ALIGN_KP × x_error`，未见 tag 时按固定速度旋转搜索 |
| **wait_for_tag_removed** | `/detections` | action 结果 | 计时器：tag 连续消失 `missing_duration_sec` 秒 → 成功 |
| **door_traverse** | `/odom` | `/cmd_vel` | 状态机：tag=1 直接前进；tag=2 倒退/等/转身/前进 |

**坐标提示**：`/cmd_vel` 类型是 `TwistStamped` 而不是 `Twist`。这是 Nav2 参数 `enable_stamped_cmd_vel: true` 决定的，手测时别发错类型。

---

### 2.4 `tourbot_perception` 感知层

**职责**：把相机原始图像变成 "tag id + 像素中心" 的结构化检测结果。

```text
tourbot_perception/
├── config/
│   └── apriltags_36h11.yaml    ← family=36h11, size=0.162, max_hamming=0
└── launch/
    └── apriltag_pipeline.launch.py
```

它本身没写算法，只是把 `apriltag_ros::apriltag_node` 启起来，并 remap：

```text
image_rect   ← /oakd/rgb/preview/image_raw
camera_info  ← /oakd/rgb/preview/camera_info
输出         → /detections
```

---

### 2.5 `tourbot_landmarks` 配置层

**职责**：用 YAML 描述地标。每个地图配一份 YAML。

```text
tourbot_landmarks/
├── config/
│   ├── cardboard_city/landmarks.yaml      ← 当前默认
│   ├── cardboard_city_old/landmarks.yaml
│   ├── repf_b4/landmarks.yaml
│   └── default/landmarks.yaml
└── tourbot_landmarks/
    └── landmarks_loader.py                 ← 一个 load_landmarks(map_name) 函数
```

**YAML 长这样**：

```yaml
home:
  tag_id: 0
  x: 0
  y: 0
  theta: NORTH

landmarks:
  - name: door_outward
    tag_id: 1
    x: 3.14
    y: 0
    theta: SOUTH
  - name: goal_3
    tag_id: 3
    x: 0.942
    y: 0.495
    theta: WEST
```

`theta` 用 8 方向字符串（NORTH/SOUTH/EAST/WEST + 四个对角），由 `TurtleBot4Directions` 枚举转角度。

---

### 2.6 `tourbot_interfaces` 接口层

**职责**：定义自定义 action 的消息结构。**它就是 .action 文件的合集**，没 Python 代码。

```text
tourbot_interfaces/
└── action/
    ├── AlignToAprilTag.action       ← 对齐 tag
    ├── WaitForTagRemoved.action     ← 等 tag 消失
    ├── DoorTraverse.action          ← 门穿越
    └── DoLandmarkTask.action        ← 占位，未接入
```

**Action 文件三段式**（用 `---` 分隔 goal / result / feedback）：

```text
# AlignToAprilTag.action
int32 tag_id
float32 timeout_sec
float32 x_tolerance_px
---
bool success
string message
---
float32 x_error_px
bool tag_visible
string state
```

---

### 2.7 第三方：`apriltag` + `apriltag_msgs` + `apriltag_ros`

**职责**：纯算法和 ROS 封装，不要改，调参在 `apriltags_36h11.yaml`。

---

## 3.包之间的依赖关系（编译顺序）

`colcon build` 会按拓扑顺序构建。Mermaid 画出来：

```mermaid
%% 包构建依赖
graph LR
    classDef thirdparty fill:"#e5e7eb",stroke:"#374151",color:"#1f2937"
    classDef interface fill:"#e9d5ff",stroke:"#5b21b6",color:"#1f2937"
    classDef impl fill:"#bbf7d0",stroke:"#166534",color:"#1f2937"
    classDef app fill:"#fde68a",stroke:"#92400e",color:"#1f2937"

    AT["apriltag"]:::thirdparty
    AM["apriltag_msgs"]:::thirdparty
    AR["apriltag_ros"]:::thirdparty

    TI["tourbot_interfaces"]:::interface
    TL["tourbot_landmarks"]:::impl
    TP["tourbot_perception"]:::impl
    TB["tourbot_behaviors"]:::impl
    TBR["tourbot_bringup"]:::impl
    TM["tourbot_mission"]:::app

    AT --> AR
    AM --> AR
    AR --> TP
    TI --> TB
    TI --> TM
    AM --> TB
    AM --> TM
    TL --> TM
    TP --> TBR
    TB --> TBR
    TM --> TBR
```

**初学者要点**：

- 修改 `.action` 文件后，**必须重新构建** `tourbot_interfaces`，否则下游 Python 进程对不上字段。
- 第三方包从源码构建会拖慢编译，建议保留 colcon 命名卷加速。

---

## 4.可执行入口一览（哪个文件能 ros2 run）

| 命令 | 对应 Python 文件 | 干什么 |
|---|---|---|
| `ros2 run tourbot_mission tour_deliberation_node` | `tour_deliberation_node.py` | 任务大脑 |
| `ros2 run tourbot_behaviors align_to_apriltag_server` | `align_to_apriltag_server.py` | 对齐 |
| `ros2 run tourbot_behaviors wait_for_tag_removed_server` | `wait_for_tag_removed_server.py` | 等门 |
| `ros2 run tourbot_behaviors door_behavior_server` | `door_behavior_server.py` | 穿门 |
| `ros2 run tourbot_bringup odom_tf_compat` | `odom_tf_compat.py` | odom→TF 兼容 |
| `ros2 run tourbot_bringup nav2_post_localization_activator` | `nav2_post_localization_activator.py` | 激活 Nav2 |

`ros2 launch` 入口看 [06-quick-reference.md](./06-quick-reference.md)。

---

## 5.改动影响范围速查

| 你想改 | 改哪里 | 影响范围 |
|---|---|---|
| 加 / 删一个地标 | `tourbot_landmarks/config/<map>/landmarks.yaml` | 只重启 mission |
| 换地图 | `tourbot_bringup/maps/` + `mission` 里 `map_name` 变量 | 重启 robot + mission |
| 调对齐参数 | `align_to_apriltag_server.py` 顶部常量 | 重启 behaviors |
| 调过门距离 | action goal 字段或 server 默认值 | 调用方/重启 server |
| 加新 action 字段 | `tourbot_interfaces/action/*.action` | 全部 rebuild |
| 改 Nav2 行为 | `tourbot_bringup/config/nav2_params.yaml` | 重启 Nav2 |
| 改容器/镜像 | `docker_stuff/Dockerfile.jazzy`、`compose.yaml` | 重建镜像 |

---

## 6.下一步

- 想看模块间 **信号怎么跑** → [02-topology.md](./02-topology.md)
- 想看 **一次完整 tour 的时序** → [03-signal-flows.md](./03-signal-flows.md)
- 想直接 **跑起来** → [04-user-guide.md](./04-user-guide.md)

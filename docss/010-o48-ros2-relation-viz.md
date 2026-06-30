# 010 · O48 ROS2 模块关系可视化：定位建图 × Topic/Action/Service × 行为树

> 适用对象：想快速看懂「机器人跑起来后，谁跟谁说话、用什么方式说」的工程师
> 数据来源：运行容器 `hyaxon-tour-guide-robot-sim-1` （镜像 `hyaxon-tour-guide-robot:jazzy`） 的实时 `ros2 node/topic/service/action` 自省，外加 `src/` 源码静态分析。
> 采集时间：2026-06-30
> 配套图：本目录 `010-o48-ros2-relation-viz.svg` （手绘分层总图，与下文 Mermaid 等价）

---

## 0.先建立三个判断

1.**代码层 ≠ 运行层**。一个包能编出多个节点；一个 launch 能串多个包。下文所有节点名都来自当前容器 `ros2 node list` 的真实输出。

2.**当前容器实际在跑的 = 定位 + Nav2 全栈**。三组 lifecycle 节点 `amcl` / `bt_navigator` / `map_server` 实测均为 `active`。`mission` 层 （`tour_deliberation_node`、`align_to_apriltag_server`、`apriltag` 等） 由 `mission.launch.py` 启动，当前未拉起，属「设计态」，下文用浅色与注释区分。

3.**四种连接方式要分清**：topic （持续数据流）、action （带反馈的长任务）、service （一问一答）、TF （坐标变换）。本文用四种线型区分。

---

## 1.系统总览（分层拓扑）

按职责分层，颜色区分层级。实线=topic，蓝=action，绿=service，红虚线=TF。

```mermaid
%% O48 运行时分层总拓扑
graph TB
    classDef sim fill:#fde68a,stroke:#92400e,color:#1f2937
    classDef loc fill:#93c5fd,stroke:#1e3a8a,color:#1f2937
    classDef nav fill:#a5b4fc,stroke:#3730a3,color:#1f2937
    classDef bt fill:#c4b5fd,stroke:#5b21b6,color:#1f2937
    classDef mis fill:#f9a8d4,stroke:#9d174d,color:#1f2937
    classDef per fill:#86efac,stroke:#166534,color:#1f2937
    classDef glue fill:#fcd34d,stroke:#b45309,color:#1f2937

    subgraph SIM["仿真层 【Gazebo + 桥接 + ros2_control】"]
        GZ["gz sim<br/>server + gui"]:::sim
        BR["ros_gz_bridge<br/>lidar / camera / pose / cmd_vel"]:::sim
        CTRL["gz_ros_control<br/>diffdrive_controller"]:::sim
        RSP["robot_state_publisher<br/>URDF → tf_static"]:::sim
        TB4["turtlebot4_node<br/>motion_control / sensors / hmi"]:::sim
    end

    subgraph LOC["定位建图层 【lifecycle_manager_localization】"]
        MAP["map_server<br/>提供 /map"]:::loc
        AMCL["amcl<br/>粒子滤波定位"]:::loc
    end

    subgraph NAV["规划控制层 【lifecycle_manager_navigation】"]
        GC["global_costmap"]:::nav
        LC["local_costmap"]:::nav
        PLN["planner_server"]:::nav
        CON["controller_server"]:::nav
        SMO["smoother_server + route_server"]:::nav
        BEH["behavior_server<br/>spin / backup / wait"]:::nav
    end

    subgraph BTL["行为树 + 速度安全链"]
        BT["bt_navigator<br/>navigate_to_pose"]:::bt
        WPF["waypoint_follower + docking_server"]:::bt
        VS["velocity_smoother"]:::bt
        CM["collision_monitor"]:::bt
    end

    subgraph MIS["任务行为感知层 【mission.launch 设计态】"]
        TDN["tour_deliberation_node"]:::mis
        ALN["align_to_apriltag_server"]:::mis
        DOOR["door_behavior_server<br/>wait_for_tag_removed_server"]:::mis
        ATAG["apriltag"]:::per
    end

    subgraph GLUE["胶水层"]
        OTC["odom_tf_compat"]:::glue
        ACTV["nav2_post_localization_activator"]:::glue
    end

    GZ -->|"/scan"| AMCL
    GZ -->|"/odom"| OTC
    GZ -->|"/odom"| CON
    BR -->|"/oakd image"| ATAG
    RSP -.->|"tf_static base_link→sensors"| AMCL
    MAP -->|"/map"| AMCL
    MAP -->|"/map"| GC
    AMCL -.->|"TF map→odom"| GC
    OTC -.->|"TF odom→base_link"| AMCL
    GC -->|"costmap"| PLN
    LC -->|"costmap"| CON
    BT -->|"act compute_path_to_pose"| PLN
    BT -->|"act follow_path"| CON
    BT -->|"act recovery"| BEH
    CON -->|"/cmd_vel_nav"| VS
    VS -->|"/cmd_vel_smoothed"| CM
    CM -->|"/cmd_vel"| BR
    TDN -->|"act navigate_to_pose"| BT
    TDN -->|"srv set_initial_pose"| AMCL
    TDN -->|"act align_to_apriltag"| ALN
    TDN -->|"act door_traverse"| DOOR
    ATAG -->|"/detections"| ALN
    ATAG -->|"/detections"| DOOR
    ALN -->|"/cmd_vel"| BR
    ACTV -->|"srv change_state"| NAV
```

---

## 2.定位建图核心数据流（已调通部分）

这是「定位建图逻辑」的核心闭环：传感器 → 定位 → TF → 代价地图。当前容器实测全部 `active`。

```mermaid
%% 定位建图核心闭环
graph LR
    classDef src fill:#fde68a,stroke:#92400e,color:#1f2937
    classDef loc fill:#93c5fd,stroke:#1e3a8a,color:#1f2937
    classDef glue fill:#fcd34d,stroke:#b45309,color:#1f2937
    classDef out fill:#a5b4fc,stroke:#3730a3,color:#1f2937

    LIDAR["gz lidar_bridge<br/>→ /scan"]:::src
    ODOM["gz odom_base_tf_bridge<br/>→ /odom"]:::src
    YAML["map_area.yaml<br/>cardboard_city"]:::src

    MAP["map_server<br/>pub /map"]:::loc
    OTC["odom_tf_compat<br/>/odom → TF"]:::glue
    AMCL["amcl<br/>粒子滤波"]:::loc

    POSE["/amcl_pose<br/>PoseWithCovariance"]:::out
    PC["/particle_cloud"]:::out
    TFMO["TF map→odom"]:::out
    GC["global_costmap"]:::out
    LC["local_costmap"]:::out

    YAML --> MAP
    LIDAR -->|"/scan"| AMCL
    ODOM --> OTC
    OTC -.->|"TF odom→base_link"| AMCL
    MAP -->|"/map"| AMCL
    AMCL --> POSE
    AMCL --> PC
    AMCL -.-> TFMO
    MAP -->|"/map"| GC
    TFMO -.-> GC
    TFMO -.-> LC
```

**关键事实（来自 `ros2 node info /amcl`）**

- 订阅：`/scan`、`/map`、`/initialpose`、`/tf`、`/tf_static`、`/clock`
- 发布：`/amcl_pose`、`/particle_cloud`、`/tf` （即 map→odom）
- 服务端：`/set_initial_pose` 【SetInitialPose】、`/reinitialize_global_localization` 【Empty】、`/request_nomotion_update` 【Empty】
- `map_server` 服务端：`/map_server/map` 【GetMap】、`/map_server/load_map` 【LoadMap】

---

## 3.TF 坐标树

定位建图的本质是补全 `map → odom → base_link` 这条链。三段由三个不同来源发布：

```mermaid
%% TF 树与发布者
graph TD
    classDef frame fill:#e0e7ff,stroke:#3730a3,color:#1f2937
    classDef pub fill:#fcd34d,stroke:#b45309,color:#1f2937

    MAPF["map"]:::frame
    ODOMF["odom"]:::frame
    BASE["base_link"]:::frame
    SENS["rplidar_link / oakd / wheels …"]:::frame

    AMCLP["amcl"]:::pub
    OTCP["odom_tf_compat"]:::pub
    RSPP["robot_state_publisher<br/>tf_static"]:::pub

    MAPF -->|"amcl 发布"| ODOMF
    ODOMF -->|"odom_tf_compat 发布"| BASE
    BASE -->|"robot_state_publisher 发布"| SENS

    AMCLP -.-> MAPF
    OTCP -.-> ODOMF
    RSPP -.-> SENS
```

> `odom_tf_compat` 存在的原因：把 `/odom` 的 pose 用 VOLATILE QoS 重发为标准 `odom→base_link` TF，让 Nav2 的 TF 监听器能正常拿到，避免 QoS 不兼容。

---

## 4.Nav2 Action / Service 拓扑

Nav2 的核心交互是 **action**。下图标出每个 server 暴露的 action，以及 `bt_navigator` 作为「编排者」如何调用下游。

```mermaid
%% Nav2 action / service 拓扑
graph TB
    classDef bt fill:#c4b5fd,stroke:#5b21b6,color:#1f2937
    classDef srv fill:#a5b4fc,stroke:#3730a3,color:#1f2937
    classDef cli fill:#f9a8d4,stroke:#9d174d,color:#1f2937

    subgraph CLIENTS["上游调用者"]
        TDN["tour_deliberation_node<br/>TurtleBot4Navigator"]:::cli
        RV["rviz2<br/>NavigateToPose 面板"]:::cli
    end

    BT["bt_navigator<br/>act-srv: navigate_to_pose ·<br/>navigate_through_poses"]:::bt

    PLN["planner_server<br/>act: compute_path_to_pose ·<br/>compute_path_through_poses<br/>srv: is_path_valid"]:::srv
    CON["controller_server<br/>act: follow_path"]:::srv
    SMO["smoother_server<br/>act: smooth_path"]:::srv
    BEH["behavior_server<br/>act: spin · backup · wait ·<br/>drive_on_heading · assisted_teleop"]:::srv
    WPF["waypoint_follower<br/>act: follow_waypoints"]:::srv
    DOCK["docking_server<br/>act: dock_robot · undock_robot"]:::srv
    ROUTE["route_server<br/>act: compute_route ·<br/>compute_and_track_route"]:::srv

    TDN -->|"navigate_to_pose"| BT
    RV -->|"navigate_to_pose"| BT
    WPF -->|"navigate_to_pose"| BT
    BT -->|"compute_path_to_pose"| PLN
    BT -->|"follow_path"| CON
    BT -->|"smooth_path"| SMO
    BT -->|"spin / backup / wait"| BEH
```

> `waypoint_follower` 内部也持 `navigate_to_pose` 的 action client，所以它既是 server 又是 client。`bt_navigator` 同理（对外 server，对自身 `navigate_to_pose` 也是 client，用于嵌套）。

---

## 5.速度指令链（cmd_vel 的层层把关）

控制输出不是直接给电机，而是经过平滑与碰撞监控两道关卡：

```mermaid
%% cmd_vel 流水线
graph LR
    classDef n fill:#a5b4fc,stroke:#3730a3,color:#1f2937
    classDef g fill:#fde68a,stroke:#92400e,color:#1f2937

    CON["controller_server"]:::n -->|"/cmd_vel_nav"| VS["velocity_smoother"]:::n
    VS -->|"/cmd_vel_smoothed"| CM["collision_monitor"]:::n
    CM -->|"/cmd_vel"| BR["ros_gz_bridge<br/>cmd_vel_bridge"]:::g
    BR -->|"Twist"| GZ["gz sim<br/>diffdrive"]:::g
    SCAN["/scan"]:::g -.->|"近距离急停"| CM
```

> 注意：`align_to_apriltag_server` 与 `door_behavior_server` 在执行精对准 / 过门时会 **直接发布 `/cmd_vel`**，绕过 Nav2 控制器，属行为层的临时接管。

---

## 6.行为树（bt_navigator 内部编排）

`nav2_params.yaml` 未指定自定义 XML，使用 Nav2 默认 `navigate_to_pose_w_replanning_and_recovery.xml`。其逻辑骨架：

```mermaid
%% bt_navigator 默认行为树骨架
graph TB
    classDef root fill:#c4b5fd,stroke:#5b21b6,color:#1f2937
    classDef ctrl fill:#ddd6fe,stroke:#5b21b6,color:#1f2937
    classDef act fill:#a5b4fc,stroke:#3730a3,color:#1f2937
    classDef rec fill:#fecaca,stroke:#b91c1c,color:#1f2937

    ROOT["RecoveryNode<br/>导航主流程"]:::root
    PIPE["PipelineSequence<br/>NavigateWithReplanning"]:::ctrl
    RATE["RateController 1Hz"]:::ctrl
    CPP["ComputePathToPose<br/>→ planner_server"]:::act
    FP["FollowPath<br/>→ controller_server"]:::act

    RECOV["RecoveryFallback<br/>恢复行为序列"]:::root
    CLR1["ClearCostmap<br/>global + local"]:::rec
    SPIN["Spin → behavior_server"]:::rec
    WAIT["Wait → behavior_server"]:::rec
    BACK["BackUp → behavior_server"]:::rec

    ROOT --> PIPE
    PIPE --> RATE
    RATE --> CPP
    PIPE --> FP
    ROOT --> RECOV
    RECOV --> CLR1
    RECOV --> SPIN
    RECOV --> WAIT
    RECOV --> BACK
```

**运行期观测点**：`/behavior_tree_log` 【nav2_msgs/BehaviorTreeLog】 持续广播每个 BT 节点的状态翻转，是调试行为树的第一手数据。

---

## 7.任务层状态机（tour_deliberation_node，设计态）

`tour_deliberation_node` 是顶层「大脑」，用贪心最近邻遍历 `landmarks.yaml`，每到一个点先对准 AprilTag，门标签则等人开门再过门：

```mermaid
%% 任务层主循环状态机
stateDiagram-v2
    [*] --> 加载landmarks
    加载landmarks --> 设置初始位姿: setInitialPose ×10
    设置初始位姿 --> 等待Nav2激活: waitUntilNav2Active
    等待Nav2激活 --> 规划遍历顺序: 贪心最近邻
    规划遍历顺序 --> 导航到下一点: startToPose → navigate_to_pose
    导航到下一点 --> 对准标签: act align_to_apriltag
    对准标签 --> 判断门标签
    判断门标签 --> 等待移除: tag_id in 1,2 · wait_for_tag_removed
    等待移除 --> 过门: act door_traverse
    判断门标签 --> 原地旋转180: 非门标签
    过门 --> 是否还有点
    原地旋转180 --> 是否还有点
    是否还有点 --> 导航到下一点: 有
    是否还有点 --> 巡游结束: 无
    巡游结束 --> [*]
```

**自定义 action 接口（`tourbot_interfaces`）**

| Action | Goal 关键字段 | Server |
|---|---|---|
| `align_to_apriltag` | tag_id · timeout_sec · x_tolerance_px | align_to_apriltag_server |
| `wait_for_tag_removed` | tag_id · timeout_sec · missing_duration_sec | wait_for_tag_removed_server |
| `door_traverse` | tag_id · backup/forward 距离与速度 | door_behavior_server |
| `do_landmark_task` | waypoint_index · expected_tag_id | landmark_task_server（备用） |

---

## 8.感知 + 行为层连接（设计态）

```mermaid
%% 感知与行为层 topic / action
graph LR
    classDef per fill:#86efac,stroke:#166534,color:#1f2937
    classDef beh fill:#f9a8d4,stroke:#9d174d,color:#1f2937
    classDef sim fill:#fde68a,stroke:#92400e,color:#1f2937

    CAM["oakd 相机<br/>/oakd/rgb/preview/image_raw"]:::sim
    CI["/oakd/rgb/preview/camera_info"]:::sim
    ATAG["apriltag<br/>apriltag_ros"]:::per
    DET["/detections<br/>AprilTagDetectionArray"]:::per

    ALN["align_to_apriltag_server"]:::beh
    WTR["wait_for_tag_removed_server"]:::beh
    DOOR["door_behavior_server"]:::beh
    CV["/cmd_vel"]:::sim
    OD["/odom"]:::sim

    CAM --> ATAG
    CI --> ATAG
    CI --> ALN
    ATAG --> DET
    DET --> ALN
    DET --> WTR
    ALN -->|"对准微调"| CV
    DOOR -->|"过门前后退/前进"| CV
    OD --> DOOR
```

> 注意 ID 约定：`tag_id` 1=外开门、2=内开门 （`is_door_tag` 判断）。`door_detector_node.py` 已注明废弃，门检测改由 `wait_for_tag_removed_server` 完成。

---

## 9.Lifecycle 激活时序

Nav2 节点都是 lifecycle 节点，必须按序 configure→activate。本工程用自定义激活器保证「先定位、后导航」：

```mermaid
%% lifecycle 激活时序
sequenceDiagram
    participant SIM as Gazebo + 桥接
    participant OTC as odom_tf_compat
    participant LML as lifecycle_manager_localization
    participant AMCL as amcl
    participant ACT as nav2_post_localization_activator
    participant LMN as lifecycle_manager_navigation
    participant BT as bt_navigator 等

    SIM->>OTC: /odom 到达
    OTC-->>SIM: 发布 TF odom→base_link
    LML->>AMCL: configure + activate
    AMCL-->>ACT: 发布 TF map→odom
    Note over ACT: 轮询 map→base_link<br/>稳定 ≥ 2s
    ACT->>LMN: 触发 change_state
    LMN->>BT: configure → activate
    Note over BT: 全栈 active 后<br/>tour_deliberation 才发首个 goal
```

> 当前容器实测：`ros2 lifecycle get /amcl|/bt_navigator|/map_server` 均返回 `active [3]`，说明该时序已成功跑完。

---

## 10.关键接口速查表

| 类别 | 名称 | 类型 | 方向 |
|---|---|---|---|
| topic | `/scan` | sensor_msgs/LaserScan | gz → amcl / collision_monitor |
| topic | `/map` | nav_msgs/OccupancyGrid | map_server → amcl / costmaps |
| topic | `/amcl_pose` | geometry_msgs/PoseWithCovarianceStamped | amcl → 观测 |
| topic | `/initialpose` | geometry_msgs/PoseWithCovarianceStamped | rviz / mission → amcl |
| topic | `/cmd_vel_nav` → `/cmd_vel_smoothed` → `/cmd_vel` | geometry_msgs/TwistStamped | controller → smoother → monitor → gz |
| topic | `/plan` · `/local_plan` | nav_msgs/Path | planner / controller → 观测 |
| topic | `/particle_cloud` | nav2_msgs/ParticleCloud | amcl → rviz |
| topic | `/behavior_tree_log` | nav2_msgs/BehaviorTreeLog | bt_navigator → 调试 |
| action | `/navigate_to_pose` | nav2_msgs/NavigateToPose | client → bt_navigator |
| action | `/compute_path_to_pose` | nav2_msgs/ComputePathToPose | bt → planner_server |
| action | `/follow_path` | nav2_msgs/FollowPath | bt → controller_server |
| action | `/spin` · `/backup` · `/wait` | nav2_msgs/* | bt → behavior_server |
| action | `/align_to_apriltag` | tourbot_interfaces/AlignToAprilTag | mission → 行为 server |
| service | `/set_initial_pose` | nav2_msgs/SetInitialPose | mission → amcl |
| service | `/map_server/load_map` | nav2_msgs/LoadMap | 运维 → map_server |
| service | `/{node}/change_state` | lifecycle_msgs/ChangeState | activator / manager → 各 lifecycle 节点 |
| TF | `map → odom` | tf2 | amcl |
| TF | `odom → base_link` | tf2 | odom_tf_compat |
| TF | `base_link → sensors` | tf2_static | robot_state_publisher |

---

## 11.复现采集的命令

```bash
C=hyaxon-tour-guide-robot-sim-1
docker exec $C bash -lc "source /opt/ros/jazzy/setup.bash; ros2 node list"
docker exec $C bash -lc "source /opt/ros/jazzy/setup.bash; ros2 topic list -t"
docker exec $C bash -lc "source /opt/ros/jazzy/setup.bash; ros2 action list -t"
docker exec $C bash -lc "source /opt/ros/jazzy/setup.bash; ros2 service list -t"
docker exec $C bash -lc "source /opt/ros/jazzy/setup.bash; ros2 node info /amcl"
docker exec $C bash -lc "source /opt/ros/jazzy/setup.bash; ros2 lifecycle get /amcl"
# 运行期看行为树翻转：
docker exec $C bash -lc "source /opt/ros/jazzy/setup.bash; ros2 topic echo /behavior_tree_log"
```

---

## 附：SVG 总图

手绘分层总图见同目录 `010-o48-ros2-relation-viz.svg`，与本文第 1 节 Mermaid 等价，可直接在浏览器打开或嵌入文档。

# 02 系统模块拓扑结构：运行时节点与数据流

> 适用对象：1-3 个月初学者
> 目标：理解机器人**跑起来之后**，哪些进程在跑、谁跟谁说话、说的是什么。

---

## 1.先建立心智模型

代码层（`src/` 下的包）和运行时（`ros2 node list` 看到的节点）**不是一回事**。一个包可以编出多个节点；一个 launch 文件可以串起若干包的节点。

本工程在 **完整仿真 + mission** 模式下，运行时大约会有这些节点：

```text
仿真层    : gz sim、ros_gz_bridge、joint_state_broadcaster、diffdrive_controller
导航层    : amcl、planner_server、controller_server、bt_navigator、behavior_server
                 waypoint_follower、velocity_smoother、map_server、lifecycle_manager_*
胶水层    : odom_tf_compat、nav2_post_localization_activator
感知层    : apriltag
行为层    : align_to_apriltag_server、wait_for_tag_removed_server、door_behavior_server
应用层    : tour_deliberation_node
可视化层  : rviz2、Gazebo GUI / HMI
```

---

## 2.系统拓扑总图

下面这张图按 **层** 摆放，颜色区分职责，箭头标 topic / action 名字。

```mermaid
%% 运行时节点拓扑
graph TB
    classDef sim fill:"#fde68a",stroke:"#92400e",color:"#1f2937"
    classDef nav fill:"#bfdbfe",stroke:"#1e3a8a",color:"#1f2937"
    classDef glue fill:"#fef3c7",stroke:"#b45309",color:"#1f2937"
    classDef per fill:"#bbf7d0",stroke:"#166534",color:"#1f2937"
    classDef beh fill:"#fbcfe8",stroke:"#9d174d",color:"#1f2937"
    classDef app fill:"#fde68a",stroke:"#7c2d12",color:"#1f2937"
    classDef viz fill:"#e9d5ff",stroke:"#5b21b6",color:"#1f2937"

    subgraph SIM["仿真层 【Gazebo】"]
        GZ["gz sim<br/>server + gui"]
        BR["ros_gz_bridge<br/>topic 桥接"]
        CTRL["diffdrive_controller<br/>joint_state_broadcaster"]
    end

    subgraph GLUE["胶水层 【兼容性】"]
        OTC["odom_tf_compat<br/>把 /odom 重发为 TF"]
        ACT["nav2_post_localization<br/>_activator<br/>激活 lifecycle"]
    end

    subgraph NAV["导航层 【Nav2】"]
        AMCL["amcl<br/>定位"]
        MAP["map_server<br/>提供 /map"]
        PLAN["planner_server<br/>全局路径"]
        CTL["controller_server<br/>局部跟踪"]
        BT["bt_navigator<br/>行为树"]
        BEH2["behavior_server<br/>恢复行为"]
        WPF["waypoint_follower"]
        VSM["velocity_smoother"]
        LCM["lifecycle_manager"]
    end

    subgraph PER["感知层"]
        APT["apriltag<br/>tag 检测"]
    end

    subgraph BEH["行为层 【自研】"]
        ALN["align_to_apriltag<br/>_server"]
        WAIT["wait_for_tag_removed<br/>_server"]
        DOOR["door_behavior_server"]
    end

    subgraph APP["应用层 【任务】"]
        TOUR["tour_deliberation_node"]
    end

    subgraph VIZ["可视化"]
        RVIZ["rviz2"]
        HMI["Turtlebot4 HMI<br/>Gazebo GUI 插件"]
    end

    GZ -->|"sensor 数据"| BR
    BR -->|"/scan /odom<br/>/oakd/rgb/preview/image_raw<br/>/oakd/rgb/preview/camera_info"| OTC
    BR -->|"/scan"| AMCL
    BR -->|"/oakd/rgb/preview/image_raw<br/>/oakd/rgb/preview/camera_info"| APT

    OTC -->|"TF: odom → base_link"| AMCL
    MAP -->|"/map"| AMCL
    AMCL -->|"TF: map → odom"| ACT
    ACT -.->|"lifecycle bringup"| LCM
    LCM -->|"激活"| AMCL
    LCM -->|"激活"| PLAN
    LCM -->|"激活"| CTL
    LCM -->|"激活"| BT
    LCM -->|"激活"| BEH2
    LCM -->|"激活"| WPF

    APT -->|"/detections"| ALN
    APT -->|"/detections"| WAIT

    TOUR -->|"action: /navigate_to_pose"| BT
    TOUR -->|"action: /align_to_apriltag"| ALN
    TOUR -->|"action: /wait_for_tag_removed"| WAIT
    TOUR -->|"action: /door_traverse"| DOOR
    TOUR -->|"/initialpose"| AMCL

    BT -->|"调用"| PLAN
    BT -->|"调用"| CTL
    BT -->|"调用"| BEH2
    CTL -->|"/cmd_vel_nav"| VSM
    VSM -->|"/cmd_vel"| CTRL

    ALN -->|"/cmd_vel"| CTRL
    DOOR -->|"/cmd_vel"| CTRL
    BR -->|"/odom"| DOOR

    CTRL -->|"驱动 joints"| GZ

    AMCL --> RVIZ
    BR --> RVIZ
    BT --> RVIZ
    GZ --> HMI

    class GZ,BR,CTRL sim
    class AMCL,MAP,PLAN,CTL,BT,BEH2,WPF,VSM,LCM nav
    class OTC,ACT glue
    class APT per
    class ALN,WAIT,DOOR beh
    class TOUR app
    class RVIZ,HMI viz
```

---

## 3.关键 topic / action 速查表

### 3.1 Topic（用 `ros2 topic list` 能看到）

| topic | 类型 | 谁发 | 谁收 | 备注 |
|---|---|---|---|---|
| `/scan` | `sensor_msgs/LaserScan` | bridge | amcl、costmap | 激光 |
| `/odom` | `nav_msgs/Odometry` | bridge | odom_tf_compat、door_server | 里程计 |
| `/tf` `/tf_static` | `tf2_msgs/TFMessage` | 多源 | 所有 | 坐标树 |
| `/map` | `nav_msgs/OccupancyGrid` | map_server | costmap、rviz | 占用栅格 |
| `/initialpose` | `geometry_msgs/PoseWithCovarianceStamped` | rviz、tour_deliberation | amcl | 设初始位姿 |
| `/cmd_vel` | `geometry_msgs/TwistStamped` ⚠ | velocity_smoother、行为 server | diffdrive_controller | **是 Stamped** |
| `/oakd/rgb/preview/image_raw` | `sensor_msgs/Image` | bridge | apriltag | 相机原图 |
| `/oakd/rgb/preview/camera_info` | `sensor_msgs/CameraInfo` | bridge | apriltag、align_server | 标定 |
| `/detections` | `apriltag_msgs/AprilTagDetectionArray` | apriltag | align、wait_server | 视觉检测 |

⚠ **新手最大坑**：手测发速度时一定用 `geometry_msgs/msg/TwistStamped`，不是 `Twist`。

### 3.2 Action

| action | 类型 | server | 调用方 |
|---|---|---|---|
| `/navigate_to_pose` | `nav2_msgs/NavigateToPose` | bt_navigator | tour_deliberation_node |
| `/align_to_apriltag` | `tourbot_interfaces/AlignToAprilTag` | align_to_apriltag_server | tour_deliberation_node |
| `/wait_for_tag_removed` | `tourbot_interfaces/WaitForTagRemoved` | wait_for_tag_removed_server | tour_deliberation_node |
| `/door_traverse` | `tourbot_interfaces/DoorTraverse` | door_behavior_server | tour_deliberation_node |

---

## 4.TF 坐标树（Nav2 能不能跑的核心）

```mermaid
%% TF 坐标系树
graph TD
    classDef world fill:"#fde68a",stroke:"#92400e",color:"#1f2937"
    classDef robot fill:"#bfdbfe",stroke:"#1e3a8a",color:"#1f2937"
    classDef sensor fill:"#bbf7d0",stroke:"#166534",color:"#1f2937"

    MAP["map<br/>全局参考系"]:::world
    ODOM["odom<br/>连续但有漂移"]:::world
    BASE["base_link<br/>机器人本体"]:::robot
    BFP["base_footprint"]:::robot
    LID["rplidar_link"]:::sensor
    CAM["oakd_rgb_camera_<br/>optical_frame"]:::sensor
    WHL["wheel_left/right_link"]:::robot

    MAP -->|"AMCL 提供"| ODOM
    ODOM -->|"odom_tf_compat 或<br/>diffdrive_controller"| BASE
    BASE --> BFP
    BASE --> LID
    BASE --> CAM
    BASE --> WHL
```

**两个常见症状**：

- `map -> odom` 缺失 → AMCL 没激活；用 RViz 2D Pose Estimate 给一次初始位姿。
- `odom -> base_link` 缺失 → 多半是 `odom_tf_compat` 没跑；查 `ros2 node list`。

---

## 5.三种典型运行配置

工程通过 **docker-compose profile + launch 组合** 提供三种"档位"：

```mermaid
%% 三种运行配置对比
graph LR
    classDef simP fill:"#fde68a",stroke:"#92400e",color:"#1f2937"
    classDef robotP fill:"#bfdbfe",stroke:"#1e3a8a",color:"#1f2937"
    classDef missionP fill:"#bbf7d0",stroke:"#166534",color:"#1f2937"

    subgraph S["sim profile<br/>compose --profile sim"]
        S1["sim.launch.py"]
        S1 --> S2["Gazebo + TB4 spawn"]
        S1 --> S3["localization + Nav2"]
        S1 --> S4["RViz2"]
        S1 --> S5["odom_tf_compat<br/>nav2_post_localization_activator"]
    end

    subgraph R["robot profile<br/>compose --profile robot"]
        R1["robot.launch.py"]
        R1 --> R2["localization"]
        R1 --> R3["Nav2"]
        R1 --> R4["RViz2"]
    end

    subgraph M["mission profile<br/>compose --profile mission"]
        M1["mission.launch.py"]
        M1 --> M2["apriltag_pipeline"]
        M1 --> M3["align_server"]
        M1 --> M4["wait_server"]
        M1 --> M5["door_server"]
        M1 --> M6["tour_deliberation"]
    end

    class S,S1,S2,S3,S4,S5 simP
    class R,R1,R2,R3,R4 robotP
    class M,M1,M2,M3,M4,M5,M6 missionP
```

**组合建议**：

| 想干嘛 | 起哪个 profile |
|---|---|
| 只看仿真和 Nav2 跑通 | `sim` 一个就够 |
| 真机导航（无 tour） | `robot` |
| 完整 tour 跑 demo | `sim` + `mission`，或 `robot` + `mission` |

**禁忌**：`sim` 内部已经带 Nav2 + RViz，不要再叠 `robot`，否则同一 `ROS_DOMAIN_ID` 下会出现两套同名 lifecycle，节点会互掐。如确需并行，用不同 `ROS_DOMAIN_ID` 隔离。

---

## 6.数据流：一个完整 landmark 的端到端

下面这张图聚焦一个 landmark 周期（导航→对齐→可能过门），方便你建立"循环"印象。

```mermaid
%% 单个 landmark 的端到端数据流
flowchart LR
    classDef inputT fill:"#bbf7d0",stroke:"#166534",color:"#1f2937"
    classDef ctrl fill:"#bfdbfe",stroke:"#1e3a8a",color:"#1f2937"
    classDef act fill:"#fde68a",stroke:"#92400e",color:"#1f2937"
    classDef out fill:"#fbcfe8",stroke:"#9d174d",color:"#1f2937"

    L["landmarks.yaml<br/>当前 landmark"]:::inputT
    SCAN["/scan"]:::inputT
    ODOM["/odom"]:::inputT
    IMG["/oakd/.../image_raw"]:::inputT

    TOUR["tour_deliberation_node"]:::ctrl
    BT2["Nav2 bt_navigator"]:::ctrl
    APT2["apriltag"]:::ctrl
    ALN2["align_server"]:::act
    WAIT2["wait_server"]:::act
    DOOR2["door_server"]:::act

    CMD["/cmd_vel<br/>TwistStamped"]:::out

    L --> TOUR
    TOUR -->|"NavigateToPose"| BT2
    SCAN --> BT2
    ODOM --> BT2
    BT2 --> CMD

    IMG --> APT2
    APT2 -->|"/detections"| ALN2
    APT2 -->|"/detections"| WAIT2
    TOUR -->|"AlignToAprilTag"| ALN2
    ALN2 --> CMD

    TOUR -->|"if tag in 1 2"| WAIT2
    WAIT2 --> TOUR
    TOUR -->|"DoorTraverse"| DOOR2
    ODOM --> DOOR2
    DOOR2 --> CMD
```

---

## 7.解耦原则（项目为什么这么切分）

把这套图记牢，就能理解架构里的几个"为什么":

- **感知/行为/任务分离**：apriltag 不知道有 tour，align_server 不知道有 door。每个 server 只看自己的输入，单测容易。
- **action 接口收窄依赖**：行为 server 之间互不通信，全靠 mission 用 action client 串。换大脑（比如换成 BT.cpp 行为树）只改 `tour_deliberation_node`。
- **landmark = 纯数据**：地标只是 YAML，换地图就换文件，不动代码。
- **launch 编排**：所有顺序、延时、参数都在 launch 里，源码不写"sleep 10 秒等别人"。

---

## 8.下一步

- 想看 **一次过门的 action 时序细节** → [03-signal-flows.md](./03-signal-flows.md)
- 想看 **代码包视角** → [01-architecture.md](./01-architecture.md)
- 想 **看节点导出的 SVG** → [07-topology.svg](./07-topology.svg)

# Tour Guide Robot 功能模块说明文档

> 编写日期：2026-06-30
> 适用对象：ROS 2 / 移动机器人导航 1-3 个月初学者
> 目标主机：`xiao-5080`
> 仓库：`tour-guide-robot`（Hyaxon fork）
> ROS 2 发行版：Jazzy

---

## 0.这是什么？

`tour-guide-robot` 是一个基于 ROS 2 Jazzy 的 **室内导游机器人** 工程。

它把一台 TurtleBot4 教学机器人变成可以自动巡游展厅的"小导游"：

- 用 **Nav2** 在已知地图上做点到点导航
- 在每个 landmark（地标）用 **AprilTag** 视觉做最终对齐
- 遇到带 tag 的"门"时，能 **等门开** 然后 **穿过去**
- 整条路线由 **YAML 配置文件** 描述
- 在 **Gazebo Harmonic** 里仿真，也支持真实机器人

工程同时提供了完整的 **Docker Compose 仿真环境**，初学者不用在主机上手装 ROS。

---

## 1.文档地图

| 序号 | 文件 | 你想做什么时看这个 |
|---|---|---|
| 01 | [01-architecture.md](./01-architecture.md) | 想看 **代码层** 怎么组织、ROS 包之间什么关系（含 Mermaid 模块图） |
| 02 | [02-topology.md](./02-topology.md) | 想从 **系统层** 看清各模块如何解耦、信号如何流动（含 Mermaid 分层图 + SVG） |
| 03 | [03-signal-flows.md](./03-signal-flows.md) | 想知道 **跑一次完整 tour** 时各节点发了啥信令（含 Mermaid 时序图） |
| 04 | [04-user-guide.md](./04-user-guide.md) | 想 **跑起来** 看到效果，不写代码 |
| 05 | [05-dev-guide.md](./05-dev-guide.md) | 想 **改代码** 增加 landmark、新行为、新地图 |
| 06 | [06-quick-reference.md](./06-quick-reference.md) | 命令、topic、action、参数 **速查表** |
| - | [topology.svg](./topology.svg) | 系统模块拓扑结构图（SVG，可直接放幻灯片） |

---

## 2.推荐阅读顺序

```text
新手第一天：
  04 用户指南  →  06 速查表  →  跑通 sim
新手第一周：
  02 拓扑结构  →  01 架构图  →  理解为什么这么分包
新手第一个月：
  03 信令流程  →  05 二次开发  →  改一个 landmark 试试
```

---

## 3.关键概念词典

为防止读后面文档时一头雾水，先把高频词说清楚：

| 词 | 通俗解释 | 在本工程的具体含义 |
|---|---|---|
| **ROS 2 节点** | 一个独立的进程，通过话题/服务/动作和别人聊天 | 每个 `*_server`、`tour_deliberation_node` 都是一个节点 |
| **Topic / 话题** | 像广播电台，发布者发，订阅者收 | 例如 `/odom`、`/scan`、`/cmd_vel` |
| **Action / 动作** | 像"叫外卖"，下单 → 进度 → 完成 | 例如 `/align_to_apriltag` |
| **Nav2** | ROS 2 的导航大礼包，含规划、控制、恢复 | 本工程导航全靠它 |
| **AprilTag** | 一种黑白方块二维码，相机识别后能知道 ID 和姿态 | 用来做 landmark 视觉确认和"开门"信号 |
| **Landmark / 地标** | 机器人想去的点 + 那里贴的 tag ID | 写在 `landmarks.yaml` |
| **Lifecycle 节点** | 有"启动 / 激活 / 失活"状态机的节点 | Nav2 的核心节点都是这种 |
| **TF** | 各坐标系之间的关系图（map → odom → base_link） | 没有它 Nav2 不工作 |
| **TwistStamped** | 带时间戳的速度指令 | 本工程 `/cmd_vel` 用这个类型，别发成 `Twist` |
| **VirtualGL / vglrun** | 把 OpenGL 从 VNC 软渲染转到物理 GPU | Gazebo 不卡顿的关键 |

---

## 4.如何在本地预览 Mermaid 图

仓库里的 `.md` 文件含 Mermaid 代码块。下面任一方式都能看到渲染后的图：

- **VS Code**：装扩展 `Markdown Preview Mermaid Support`，按 `Ctrl+Shift+V`
- **GitHub / GitLab Web**：直接打开 `.md` 文件，原生支持
- **在线**：复制代码到 <https://mermaid.live>

SVG 图（`topology.svg`）任何浏览器或图形软件都能直接打开。

---

## 5.关键参考文件清单

> 当文档中提到代码位置时，对应的真实路径在这里。

```text
src/tourbot_bringup/launch/sim.launch.py          仿真总入口
src/tourbot_bringup/launch/robot.launch.py        真机/导航栈
src/tourbot_bringup/launch/mission.launch.py      任务 + 感知 + 行为
src/tourbot_mission/tourbot_mission/tour_deliberation_node.py   任务主循环
src/tourbot_behaviors/tourbot_behaviors/align_to_apriltag_server.py
src/tourbot_behaviors/tourbot_behaviors/wait_for_tag_removed_server.py
src/tourbot_behaviors/tourbot_behaviors/door_behavior_server.py
src/tourbot_perception/launch/apriltag_pipeline.launch.py
src/tourbot_perception/config/apriltags_36h11.yaml
src/tourbot_landmarks/config/cardboard_city/landmarks.yaml
src/tourbot_interfaces/action/*.action            自定义 action 接口
docker_stuff/compose.yaml                         容器编排
docker_stuff/Dockerfile.jazzy                     镜像构建
```

---

## 6.许可与声明

- 原始代码 MIT License，详见 `LICENSE`。
- 含第三方组件（`apriltag`、`apriltag_ros`、`apriltag_msgs`），各自许可见 `THIRD_PARTY_NOTICES.md`。
- 本文档为内部学习材料，欢迎在内部分享。

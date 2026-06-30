# 011 · cardboard_city + AprilTag world 溯源与开源替代调查

> 文档编号:011-o48 · 日期:2026-06-30
> 目标仓库:`imaxwel/Hyaxon-tour-guide-robot`(本地工程 `~/4sim/gh-ref/tour-guide-robot/Hyaxon-tour-guide-robot`)
> 读者:项目经理 / CTO
> 方法:本地仓库取证(world.sdf / landmarks.yaml / git 历史)+ 全网英文为主、中文为辅的开源检索

---

## 0. 先重述你的真实意图(确认理解)

你问的不是"AprilTag 是什么"这种科普,而是一个**溯源(provenance)问题**:

> 本仓库反复提到的 `cardboard_city` world / map(带 AprilTag landmark),到底是
> **这个项目原创自造的**,还是 **复用 / fork / 抄自互联网上某个已存在的开源仿真世界或模型仓库**?
> 如果是后者,把它的**上游源头**(GitHub/GitLab 仓库、模型文件、论文/数据集)查到链路完整、没有悬念为止;
> 如果是前者,明确证伪,并给出**能用来真正把它补完的开源砖块**。

下面的结论分两段交付:**(A) 本仓库 cardboard_city 的真实身份**,**(B) 全网是否存在可直接复用的开源资产**。两段都给到可验证的证据,不留"悬而未决"。

---

## 1. 一句话结论(TL;DR)

- **不存在**一个叫 `cardboard_city` 的开源 Gazebo world 仓库/模型可供下载。全网英文 + 中文检索均无命中。
- 本仓库的 `cardboard_city` 是 **两样东西的拼装**,都不是开源资产:
  1. 一个 **自建且未完成** 的 Gazebo world(`world.sdf`,仅 153 行,只有地面 + 光照 + GUI + 基础插件,**没有墙、门、纸箱、AprilTag**)——**README 自己承认没做完**;
  2. 一张 **真实物理场地** 的 SLAM 栅格地图(`map_area.pgm`)+ 手写的 landmark/AprilTag 坐标(`landmarks.yaml`)。这张"cardboard city"是团队**用纸箱在现实里搭的测试场**,不是虚拟世界。
- 因此正确的问题不是"去哪儿下载 cardboard_city world",而是"**用哪些开源砖块把它补完**"。这些砖块确实是开源的、成熟的,核心是 **`koide3/gazebo_apriltag`**(及其 Gazebo Harmonic 分支 `rickarmstrong/gazebo_apriltag@harmonic`)。

> 👀 一个大家没注意到的点:`landmarks.yaml` 里的注释写着 `Box 1 Left (Close to home)`、`Center Box Right Side`——这些是**真实的纸箱**。所谓 "cardboard city"(纸板城)字面意思就是**一堆纸箱摆成的微缩城市**,机器人在里面跑一圈 SLAM 出 `map_area.pgm`。这不是隐喻,也不是某个知名虚拟世界的代号。

---

## 2. 取证:本仓库 cardboard_city 到底是什么

### 2.1 world 文件:自建、极简、未完成

`src/tourbot_bringup/worlds/cardboard_city/world.sdf`,共 **153 行**,内容拆解:

| 区块 | 内容 | 是否场景资产 |
|---|---|---|
| `<physics>` | ODE,1ms 步长 | 框架 |
| `<plugin>` ×6 | physics / user-commands / scene-broadcaster / sensors(ogre2)/ imu | Gazebo Sim 系统插件 |
| `<gui>` | MinimalScene / InteractiveViewControl / SelectEntities | 纯界面 |
| `<light name="sun">` | 一盏平行光 | 框架 |
| `<include>` | `Ground Plane`(来自 Gazebo Fuel) | **唯一外部模型,也只是地面** |
| 注释 `These walls establish...` | **后面是空的** | ❌ 墙体根本没放 |

也就是说:**world 里没有任何 cardboard、门或 AprilTag 模型**。这与文档 007 第 4.3 节、008 指南、以及 README 第 261 行的说法完全一致:

> README L261:*"No custom Gazebo world was fully completed for the cardboard city environment."*
> (没有为 cardboard city 环境完整做出自定义 Gazebo 世界。)

唯一引用的外部资源是 Gazebo Fuel 的 **Ground Plane**(`https://fuel.gazebosim.org/1.0/OpenRobotics/models/Ground Plane`)——这是官方公共资产,但它只是地板,与"cardboard_city"无关。

### 2.2 landmark / AprilTag:手写坐标,对应真实纸箱

`src/tourbot_landmarks/config/cardboard_city/landmarks.yaml`:

| name | tag_id | x | y | theta | 注释里的真实物体 |
|---|---|---|---|---|---|
| home | 0 | 0 | 0 | NORTH | 起点 |
| door_outward | 1 | 3.14 | 0 | SOUTH | 门(外向) |
| door_inward | 2 | 1.71 | 0 | NORTH | 门(内向) |
| goal_3 | 3 | 0.942 | 0.495 | WEST | **Box 1 Left** |
| goal_4 | 4 | 1.33 | -0.2 | EAST | **Box 2 Right** |
| goal_5 | 5 | 3.36 | -0.2 | EAST | **Box 3 Right** |
| goal_6 | 6 | 2.34 | -0.647 | WEST | **Center Box Right Side** |
| goal_7 | 7 | 2.35 | 0.673 | EAST | **Center Box Left Side** |

- AprilTag 家族:`src/tourbot_perception/config/apriltags_36h11.yaml` → **family 36h11,size 0.162 m**(标准 16cm 标签)。
- 这些坐标是**米制实测/手填**,不是某个程序化世界生成的;`tag_id 0–7` 与门/纸箱一一对应,是为**现实场地里贴的实体标签**准备的。

### 2.3 地图:真实 SLAM 产物

`src/tourbot_bringup/maps/cardboard_city/map_area.yaml`:
```
image: map_area.pgm   resolution: 0.050   origin: [-8.254, -2.080, 0]
mode: trinary   occupied_thresh: 0.65   free_thresh: 0.196
```
`map_area.pgm` 36 KB,标准 Nav2 占据栅格。`resolution 0.05`、trinary、非整的 `origin`——这是**真机跑 SLAM(LiDAR/RPLIDAR)出来的实测地图**特征,而非从虚拟世界一键导出的规整地图。README 也印证传感器是 RPLIDAR + OAK-D。

### 2.4 git 取证:私有原创,无 fork 痕迹

- `origin` = `git@github.com:imaxwel/Hyaxon-tour-guide-robot.git`,**单一 remote,无 upstream**。
- 首提交 `12c5a4e Initial commit`(2026-04-10),作者 **Hyde / Hyaxon**(`108911977+Hyaxon`),后续 commit 全是同一作者手工演进:`Cardboard city landmarks added`→`New landmarks`→`Door distance fixes` 等。
- commit 信息里**没有任何 "fork / based on / import / vendored" 字样**;world.sdf / landmarks.yaml **没有上游 author/source 注释**。

**结论:cardboard_city 是该项目作者原创的、围绕一个现实纸箱场地手工搭建的资产组合;不是从任何开源世界 fork 或下载来的。** world 部分甚至还没做完。

---

## 3. 全网检索:有没有现成的开源 "cardboard_city + AprilTag" world?

**没有。** 用多组英文 + 中文关键词检索(GitHub/GitLab/Fuel/通用搜索),**无任何**叫 `cardboard_city` / "cardboard city" 的 AprilTag Gazebo world 仓库或模型。最接近"tour guide robot"的开源项目是 IIT 的 [`hsp-iit/tour-guide-robot`](https://github.com/hsp-iit/tour-guide-robot),但那是 **R1 人形机器人**平台,与本仓库的 TurtleBot4 + cardboard 场地毫无关系,**不是上游**。

换句话说:**这条"找现成 world"的线索到此为止——它本来就不存在。** 真正有价值的是下面这批**可复用的开源砖块**,它们能把本仓库缺失的 world 补完。

---

## 4. 能用来"补完"cardboard_city world 的开源资产(核心交付)

按"对本仓库的适配度"排序。本仓库用的是 **Gazebo Sim(`gz-sim-*` 插件,ogre2)**,对应 TurtleBot4 Jazzy 栈 = **Gazebo Harmonic**——这决定了选型(见 ⚠️ 标注)。

| # | 仓库 / 资产 | 提供什么 | 标签家族 | 适配 Gazebo 版本 | 对本仓库的用法 |
|---|---|---|---|---|---|
| 1 | [`koide3/gazebo_apriltag`](https://github.com/koide3/gazebo_apriltag) | AprilTag 的 Gazebo 模型 + `generate.py` 批量生成脚本(90★) | 36h11(可改) | Classic / Ignition | **事实标准**。生成 `tag36_11_00000…` 模型 |
| 2 | [`rickarmstrong/gazebo_apriltag@harmonic`](https://github.com/rickarmstrong/gazebo_apriltag/tree/harmonic) | 上者的 **Harmonic 分支** | 36h11 | **Harmonic ✅** | ⚠️ **本仓库应优先用这个分支** |
| 3 | [`benediktkreis/apriltag_to_ignition_gazebo`](https://github.com/benediktkreis/apriltag_to_ignition_gazebo) | AprilTag 3 的 Ignition/Gazebo 模型 | 多家族 | Ignition/Sim | Harmonic 路线的备选 |
| 4 | [`TAMS-Group/tams_apriltags`](https://github.com/TAMS-Group/tams_apriltags) | 薄卡片 URDF + collada 贴图,含 16h5 & 36h11 **全套** | 16h5 + 36h11 | 各版本 + RViz | 想要"卡片实体"而非贴纸面片时用 |
| 5 | [`rfzeg/apriltag_robot_pose`](https://github.com/rfzeg/apriltag_robot_pose) | 含 AprilTag 的现成 world(`plywood_mazes`)+ 基于 tag 的定位 | 36h11 | Classic | 参考"把 tag 放进 world 做 landmark 定位"的完整范式 |
| 6 | [`mintforpeople/robobo-gazebo-simulator`](https://github.com/mintforpeople/robobo-gazebo-simulator) | `city_arucos` / `table`(纸箱+标记)等 world | ArUco/QR | Classic | **思路最接近**"纸箱+标记的城市",但用 ArUco 非 AprilTag |
| 7 | [Gazebo Fuel](https://app.gazebosim.org/fuel) `Ground Plane` 等 | 官方公共模型库 | — | Sim/Harmonic | 本仓库已用其 Ground Plane;墙/箱可在此找 |
| 8 | [`turtlebot4_simulator`](https://github.com/turtlebot/turtlebot4_simulator) | TurtleBot4 官方仿真;自定义 world 需源码编译并放入 | — | Harmonic | 装 custom world 的**官方落地方式** |

补充参考(教程/课程,非资产但是最佳"装配蓝图"):
- [automaticaddison · Nav2 + AprilTag 自主对接(ROS 2 Jazzy)](https://automaticaddison.com/autonomous-docking-with-apriltags-using-nav2-ros-2-jazzy/):**端到端最贴近本仓库**的集成教程——在 world 里放 tag、用 `apriltag_ros` 出位姿、喂给 Nav2 Docking Server 的 `SimpleChargingDock`。本仓库的 `align_to_apriltag` 行为可直接对标。
- [`YuehChuan/tb3_aprilTag`](https://github.com/YuehChuan/tb3_aprilTag):TurtleBot3 的 AprilTag 仿真(偏老,Kinetic/Gazebo8),仅作管线参考。
- [HackMD · AprilTag localization note](https://hackmd.io/@ncrl-11/SJUXcmD59):实战坑——tag 在 Gazebo 里发灰要把 model.sdf 的 `lighting` 设 0;tag 会掉落要设 `static true`。

### ⚠️ 选型要点(直接影响能否跑起来)

1. **版本对齐**:本仓库 world.sdf 用的是 `gz-sim-*` 系统插件 + `ogre2` → **Gazebo Harmonic/Sim**。所以:
   - 环境变量用 **`GZ_SIM_RESOURCE_PATH`**,**不是**经典的 `GAZEBO_MODEL_PATH`;
   - AprilTag 模型优先取 **#2 的 `@harmonic` 分支**或 **#3**,直接用 koide3 master(为 Classic 写)可能贴图/材质不兼容。
2. **tag 尺寸要一致**:本仓库 `apriltags_36h11.yaml` 写死 `size: 0.162`(16.2 cm)。放进 world 的 tag 物理边长必须与之匹配,否则 `apriltag_ros` 解出的距离会系统性偏差(koide3 issue#1 正是在讨论 tag_size 单位)。
3. **tag_id 要对上 landmarks.yaml**:world 里至少要放 **id 0–7** 共 8 个 36h11 tag,坐标按 §2.2 的表摆放,门用 1/2、纸箱用 3–7。

---

## 5. 给 PM / CTO 的决策结论

| 问题 | 结论 |
|---|---|
| cardboard_city world 是开源现成货吗? | **不是**。全网无此资产;本仓库是原创且 world 未完成。 |
| 它有上游/fork 吗? | **没有**。单一作者(Hyaxon)私有原创,无 upstream、无 vendored 注释。 |
| "cardboard city" 是什么? | **现实里用纸箱搭的微缩测试场**,机器人 SLAM 出 `map_area.pgm`;landmarks 是贴在纸箱/门上的实体 AprilTag。 |
| 那现在 world 能跑完整自动 tour 吗? | **不能**。world 里没有 tag 模型,mission 在 align 阶段会一直搜索到 timeout(文档 007/008 已记录)。 |
| 怎么补完?成本? | 拉 **#2 `rickarmstrong/gazebo_apriltag@harmonic`** 生成 36h11 tag,按 `landmarks.yaml` 坐标 `<include>` 进 `world.sdf`,加几面墙/门(Fuel 或自写 SDF)。**1 人天级**工作,无需自研。 |
| 有没有"更省事"的整体替代? | 若可放弃"复刻现实纸箱场",直接用 `turtlebot4_simulator` 官方 world + #2 的 tag 做一个**新** landmark 世界,比硬补现有 world 更干净。但地图/landmark 要重做。 |

---

## 6. 附:取证命令(可复现)

```bash
cd ~/4sim/gh-ref/tour-guide-robot/Hyaxon-tour-guide-robot
wc -l src/tourbot_bringup/worlds/cardboard_city/world.sdf          # 153 行
grep -n include src/tourbot_bringup/worlds/cardboard_city/world.sdf # 仅 Ground Plane
cat  src/tourbot_landmarks/config/cardboard_city/landmarks.yaml     # Box/door 注释 + tag_id 0-7
cat  src/tourbot_perception/config/apriltags_36h11.yaml             # family 36h11, size 0.162
git remote -v                                                      # 仅 origin,无 upstream
git log --reverse --format='%h %an %s' | head                      # Hyaxon 单作者原创
grep -n "No custom Gazebo world" README.md                          # README 自承认 world 未完成
```

---

## 7. 参考来源(Sources)

- [koide3/gazebo_apriltag](https://github.com/koide3/gazebo_apriltag) · [generate.py](https://github.com/koide3/gazebo_apriltag/blob/master/generate.py) · [issue#1 tag_size](https://github.com/koide3/gazebo_apriltag/issues/1)
- [rickarmstrong/gazebo_apriltag@harmonic](https://github.com/rickarmstrong/gazebo_apriltag/tree/harmonic)
- [benediktkreis/apriltag_to_ignition_gazebo](https://github.com/benediktkreis/apriltag_to_ignition_gazebo)
- [TAMS-Group/tams_apriltags](https://github.com/TAMS-Group/tams_apriltags)
- [rfzeg/apriltag_robot_pose](https://github.com/rfzeg/apriltag_robot_pose)
- [mintforpeople/robobo-gazebo-simulator](https://github.com/mintforpeople/robobo-gazebo-simulator)
- [hsp-iit/tour-guide-robot](https://github.com/hsp-iit/tour-guide-robot)(R1 平台,非本仓库上游)
- [YuehChuan/tb3_aprilTag](https://github.com/YuehChuan/tb3_aprilTag)
- [turtlebot4_simulator](https://github.com/turtlebot/turtlebot4_simulator) · [TurtleBot4 Simulator 手册](https://turtlebot.github.io/turtlebot4-user-manual/software/turtlebot4_simulator.html)
- [automaticaddison · Nav2 + AprilTag Docking (Jazzy)](https://automaticaddison.com/autonomous-docking-with-apriltags-using-nav2-ros-2-jazzy/)
- [HackMD · AprilTag localization note](https://hackmd.io/@ncrl-11/SJUXcmD59)
- [Gazebo Fuel 模型库](https://app.gazebosim.org/fuel)

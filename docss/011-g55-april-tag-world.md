# 011 · G55 AprilTag cardboard_city world 开源资产检索

> 结论日期：2026-06-30  
> 工程位置：`~/4sim/gh-ref/tour-guide-robot/Hyaxon-tour-guide-robot`  
> 问题：公开网络上是否存在可直接替换当前仓库 `cardboard_city` 的、带 AprilTag 的完整 Gazebo world / map / model 仓库？

## 0.结论

没有检索到一个公开可访问、能直接对应当前仓库 `cardboard_city` 的完整开源场景仓库。

更具体地说，没有找到同时满足以下条件的公开资产：

- 名称或路径与 `cardboard_city` / `tourbot_bringup/worlds/cardboard_city` 对应。
- 包含完整 cardboard city 墙体、障碍物、门结构。
- 已放置与当前 `landmarks.yaml` 中 `tag_id: 0..7` 匹配的 AprilTag 36h11 模型。
- 能直接作为当前 `sim.launch.py` 的 `custom_world` 使用。

能找到并可复用的是通用 AprilTag Gazebo 模型仓库，例如 `koide3/gazebo_apriltag` 及其 Gazebo Harmonic 分支/派生。它们可以提供 tag 平面模型或生成脚本，但不是 `cardboard_city` world，也不包含当前地图中的墙、门和 landmark 布局。

因此，当前仓库若要实现视觉闭环 tour，需要在现有 `world.sdf` 中补齐场景几何和 AprilTag，或者继续使用 topic/action 级仿真注入 `/detections` 做功能验证。

## 1.当前仓库基线

当前远端工程中实际存在的 world 是：

```text
src/tourbot_bringup/worlds/cardboard_city/world.sdf
```

该文件的有效场景内容只有 Gazebo 系统插件、GUI、太阳光和 OpenRobotics `Ground Plane`。文件末尾只有占位注释：

```xml
<!-- These walls establish the location of the simulation based on the project -->
```

也就是说，`world.sdf` 里尚无墙体、门、箱体、障碍物或 AprilTag `<include>` / `<model>`。

当前 landmark 配置需要 8 个 tag：

| 用途 | tag_id | 坐标 / 方向 |
|---|---:|---|
| home | 0 | `(0, 0)`, NORTH |
| door_outward | 1 | `(3.14, 0)`, SOUTH |
| door_inward | 2 | `(1.71, 0)`, NORTH |
| goal_3 | 3 | `(0.942, 0.495)`, WEST |
| goal_4 | 4 | `(1.33, -0.2)`, EAST |
| goal_5 | 5 | `(3.36, -0.2)`, EAST |
| goal_6 | 6 | `(2.34, -0.647)`, WEST |
| goal_7 | 7 | `(2.35, 0.673)`, EAST |

AprilTag pipeline 配置为：

```yaml
family: 36h11
size: 0.162
max_hamming: 0
z_up: true
```

这意味着可见模型最好使用 `tag36h11` / `36_11`，并将实际物理边长设为约 `0.162 m`，否则相机检测和 pose 估计会与行为层假设不一致。

## 2.联网检索结果

| 检索对象 | 检索方式 | 结果 |
|---|---|---|
| `cardboard_city` 精确字符串 | Web 搜索 + GitHub code search 链接复核 | 公开网页未发现可用 world；GitHub 未登录 code search 页面不展示代码结果，因此这部分不能作为绝对穷尽证明。 |
| `tourbot_bringup` + `cardboard_city` | Web 搜索 + GitHub code search 链接复核 | 公开网页未发现同名 ROS/Gazebo 工程。 |
| `door_outward` + `tag_id` | Web 搜索 + GitHub code search 链接复核 | 公开网页未发现同一组 landmark/tag 配置；该命名没有找到可公开复用来源。 |
| `cardboard_city` 仓库名 | GitHub repository API/search | 只出现无关的 `cardboardcity-webgui` 等项目；不是 ROS/Gazebo world。 |
| `cardboard_city gazebo` / `cardboardcity gazebo` | GitHub repository API/search | 结果为 0。 |
| `Hyaxon-tour-guide-robot` | GitHub repository API/search | 结果为 0；当前远端 origin 看起来不是公开可检索仓库。 |
| `AprilTag Gazebo model` | GitHub/web 检索 | 找到通用 AprilTag 模型仓库，见下一节。 |

这些检索不能证明互联网绝对不存在未索引、私有或需要登录才能检出的资产；但足以判断：没有找到可以直接声明为“当前仓库所缺失的开源 `cardboard_city` + AprilTag 完整 world”的公开来源。

## 3.可复用开源资产

### 3.1 `koide3/gazebo_apriltag`

链接：<https://github.com/koide3/gazebo_apriltag>

用途：Gazebo AprilTag 模型集合。GitHub 仓库描述为 “Apriltag models for gazebo”。仓库中包含 `models/Apriltag36_11_00000`、`models/Apriltag36_11_00001` 等目录，每个 tag 模型带 `model.sdf`、材质脚本和纹理。

典型模型结构：

```text
models/Apriltag36_11_00001/
  model.config
  model.sdf
  materials/
    scripts/Apriltag.material
    textures/tag36_11_00001.png
```

限制：

- 这是 AprilTag 模型包，不是 cardboard city world。
- 默认模型 `model.sdf` 是 SDF 1.6 / Gazebo Classic 风格，纹理通过 OGRE material script 引入。
- 当前工程使用 ROS 2 Jazzy + Gazebo Harmonic 风格插件时，应先验证纹理能否在 `gz sim` 中正常渲染。

### 3.2 `rickarmstrong/gazebo_apriltag` harmonic 分支

链接：<https://github.com/rickarmstrong/gazebo_apriltag/tree/harmonic>

用途：面向 Gazebo Harmonic 生成 AprilTag 模型。README 明确写到该分支生成兼容 Gazebo Harmonic 的 AprilTag 模型，并建议把模型路径加入 `GZ_SIM_RESOURCE_PATH`。

限制：

- 该分支主要提供模板和 `generate.py`，不是预置完整 `models/Apriltag36_11_00000..` 的 world 包。
- 同样不包含 `cardboard_city` 的墙、门、地图或 landmark 布局。

### 3.3 Gazebo 官方资源

链接：<https://github.com/gazebosim/gz-sim>

当前 `world.sdf` 已通过 Fuel URI 引用了 OpenRobotics `Ground Plane`：

```xml
<uri>https://fuel.gazebosim.org/1.0/OpenRobotics/models/Ground Plane</uri>
```

这只能提供地面。Gazebo 官方资源不能补齐本项目特定的 cardboard city 布局和 AprilTag 放置。

## 4.对当前仓库的影响

当前 `cardboard_city` 地图和 `landmarks.yaml` 更像是从真实或课程环境采集/手写出来的导航数据，而不是从一个完整开源 Gazebo world 同步而来。

证据：

- `world.sdf` 只有占位注释，没有场景几何。
- `landmarks.yaml` 已经定义了 tag 编号、坐标和朝向。
- `apriltags_36h11.yaml` 已经定义 tag family 和尺寸。
- 公开检索没有找到同名 world 或同一组 landmark/tag 配置。

所以自动 tour 卡在 AprilTag 对齐阶段时，根因应视为“仿真场景资产缺失”，不是 `apriltag_ros`、action server 或 Nav2 框架缺失。

## 5.建议路径

优先路径：

1. 使用 `rickarmstrong/gazebo_apriltag` 的 harmonic 分支或自行生成 SDF 1.9/PBR tag 模型。
2. 生成 `tag36_11_00000` 到 `tag36_11_00007`，尺寸设为 `0.162 m`。
3. 在 `src/tourbot_bringup/worlds/cardboard_city/world.sdf` 中按 `landmarks.yaml` 坐标补 `<include>`。
4. 根据 `theta` 调整 tag 法线朝向，使 TurtleBot4 到达对应 landmark 时相机能正面看到 tag。
5. 补墙体、门和障碍物时，以 `map_area.yaml` / `map_area.pgm` 为依据，确保 Gazebo 几何与 Nav2 静态地图一致。

短期验证路径：

继续使用现有文档第 7 节的 topic/action 方法，向 `/detections` 发布合成 `AprilTagDetectionArray`，先验证：

- `/align_to_apriltag`
- `/wait_for_tag_removed`
- `/door_traverse`
- `tour_deliberation_node` 的任务编排

这条路径不能验证视觉识别和相机几何，但能验证 mission 行为层是否按预期工作。

## 6.最小可落地改造草案

如果只想让 mission 至少完成一个 landmark + align 闭环，可以先只补一个 tag：

```xml
<include>
  <name>tag36_11_00003</name>
  <uri>model://tag36_11_00003</uri>
  <!-- 需要按相机视角微调 z 和 yaw；这里不能直接照抄为最终值 -->
  <pose>0.942 0.495 0.35 0 0 1.5708</pose>
</include>
```

注意：

- `<uri>` 的模型名必须与实际模型目录一致；`koide3` 默认是 `Apriltag36_11_00003`，harmonic 生成模板默认可能是 `tag36_11_00003`。
- `pose` 中 yaw 需要根据 tag 的可见面法线和机器人到达姿态调试。
- 如果 tag 是竖直贴墙，应使用一个薄盒或墙面作为物理/视觉载体，而不是只把 tag 平放在地上。
- 加入 tag 后需要用 Gazebo 相机图像确认 tag 纹理未丢失、未镜像、未被墙体遮挡。

## 7.来源链接

- GitHub code search: `cardboard_city`：<https://github.com/search?q=%22cardboard_city%22&type=code>
- GitHub code search: `tourbot_bringup` + `cardboard_city`：<https://github.com/search?q=%22tourbot_bringup%22+%22cardboard_city%22&type=code>
- GitHub code search: `door_outward` + `tag_id`：<https://github.com/search?q=%22door_outward%22+%22tag_id%22&type=code>
- `koide3/gazebo_apriltag`：<https://github.com/koide3/gazebo_apriltag>
- `rickarmstrong/gazebo_apriltag` harmonic 分支：<https://github.com/rickarmstrong/gazebo_apriltag/tree/harmonic>
- Gazebo Sim：<https://github.com/gazebosim/gz-sim>

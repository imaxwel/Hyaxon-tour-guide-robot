# 101 - TurboVNC 远程桌面低帧率排查与修复

日期：2026-05-13  
主机：5080-MS-eSport-Z890M (192.168.100.55)  
GPU：NVIDIA GeForce RTX 5080

---

## 1. 问题现象

通过 SSH tunnel 连接 TurboVNC Viewer 到 5921 端口：

```bash
ssh -N -L 5921:127.0.0.1:5921 maxw@192.168.100.55
```

画面一卡一卡，帧率极低，带宽占用远低于预期。  
对比同一台机器上 hongzt 的 :5913 连接非常流畅（~10MBps 带宽，高帧率）。

---

## 2. 排查过程

### 2.1 确认 VNC 服务端类型

```bash
ps aux | grep 5921
```

发现 5921 端口实际运行的是 **x11vnc**，不是 TurboVNC Xvnc：

```
maxw /usr/bin/x11vnc -display :21 -auth /tmp/.docker-go2-isaac-ros2-vnc21.xauth \
  -rfbauth /home/maxw/.vnc/go2-isaac-ros2-x11vnc.pass \
  -localhost -rfbport 5921 -forever -shared -repeat -noxdamage
```

而 hongzt 流畅的 5913 端口用的是 TurboVNC Xvnc：

```
hongzt /opt/TurboVNC/bin/Xvnc :13 -deferupdate 1 -geometry 1920x1200 -depth 24 \
  -dridir /usr/lib/x86_64-linux-gnu/dri -registrydir /usr/lib/xorg -localhost ...
```

### 2.2 分析性能差异根因

| 维度 | x11vnc (旧 5921) | TurboVNC Xvnc (hongzt 5913) |
|------|-------------------|------------------------------|
| 架构 | 附着到已有 Xorg，屏幕抓取 | 自身就是 X server，拥有 framebuffer |
| 编码器 | 标准 libvncserver，单线程 | TurboVNC 优化 Tight，多线程（每核一线程） |
| JPEG 压缩 | 基础 libjpeg | libjpeg-turbo（SIMD 加速） |
| 帧更新延迟 | `-defer 20ms -wait 20ms`（默认） | `-deferupdate 1`（1ms） |
| 变化检测 | `-noxdamage` 全屏轮询对比 | 内建 framebuffer，直接知道脏区域 |
| 理论最大帧率 | ~25fps（受 defer+wait 限制） | ~1000fps（仅受编码速度限制） |

### 2.3 原理解释

**x11vnc 的瓶颈链路：**

```
GPU 渲染 → Xorg framebuffer → x11vnc 全屏轮询读取 → 单线程 Tight 编码 → 网络
                                    ↑ 20ms 间隔              ↑ 慢
```

- `-noxdamage` 禁用了 X DAMAGE 扩展，x11vnc 无法知道哪些像素变化，必须每 20ms 全屏扫描对比
- 2560×1440×4 bytes = 14.7MB 每帧需要读取和对比，CPU 开销大
- 单线程编码无法充分利用多核 CPU

**TurboVNC Xvnc 的高效链路：**

```
应用直接渲染到 Xvnc framebuffer → 精确脏区域追踪 → 多线程 Tight+JPEG 编码 → 网络
                                        ↑ 1ms 延迟        ↑ 快
```

- Xvnc 自身就是 X server，framebuffer 就在进程内存中，零拷贝
- 精确知道哪些矩形区域被修改，只编码脏区域
- 多线程 Tight 编码 + libjpeg-turbo SIMD，编码吞吐量高数倍

---

## 3. 解决方案

### 3.1 方案选择

照搬 hongzt :13 方案：用 TurboVNC Xvnc 替代 x11vnc + Xorg :21。

### 3.2 实施步骤

```bash
# 停掉旧服务
pkill -f "x11vnc.*5921"
sudo pkill -f "Xorg :21"

# 启动 TurboVNC（Xfce4 桌面）
cd /home/maxw/4sim/go2
./scripts/start-go2-turbovnc-vnc21.sh
```

### 3.3 启动脚本

`/home/maxw/4sim/go2/scripts/start-go2-turbovnc-vnc21.sh`

关键参数（与 hongzt 一致）：

```bash
/opt/TurboVNC/bin/vncserver :21 \
  -geometry 2560x1440 \
  -depth 24 \
  -deferupdate 1 \
  -dridir /usr/lib/x86_64-linux-gnu/dri \
  -registrydir /usr/lib/xorg \
  -localhost \
  -xstartup /home/maxw/.vnc/xstartup.turbovnc
```

### 3.4 踩坑：桌面环境选择

首次启动时未指定 `-xstartup`，TurboVNC vncserver 自动检测到系统 `/usr/share/xsessions/ubuntu.desktop`，启动了 GNOME 桌面（重且不适合 VNC）。

修复：显式指定 `-xstartup /home/maxw/.vnc/xstartup.turbovnc` 强制使用 Xfce4。

`~/.vnc/xstartup.turbovnc` 内容要点：
- 设置 `XDG_CURRENT_DESKTOP=XFCE`
- 通过 `dbus-run-session` 启动 xfwm4、xfdesktop、xfce4-panel 等组件
- 与 hongzt 的配置完全一致

### 3.5 GPU 硬件加速（MuJoCo 等 OpenGL 应用）

TurboVNC Xvnc 是虚拟 X server，自身不具备 GPU 渲染能力。OpenGL 应用需要通过 VirtualGL 将渲染重定向到物理 GPU：

```bash
DISPLAY=:21 vglrun -d :0 ./unitree_mujoco -i 0 -r g1 -s scene_29dof.xml
```

原理：
```
应用 OpenGL 调用 → VirtualGL 拦截 → 物理 GPU (Xorg :0) 渲染 → 像素回传 → TurboVNC Xvnc :21 显示
```

注意：Isaac Sim (RTX/Vulkan) 不支持 VirtualGL，仍需真实 Xorg display。

---

## 4. 验证

```bash
# 确认 TurboVNC Xvnc 运行
ps aux | grep "Xvnc.*:21"

# 确认端口监听
ss -tlnp 'sport = :5921'

# 确认 Xfce4 桌面
ps aux | grep -E "xfwm4|xfce4-panel" | grep maxw

# 客户端连接
ssh -N -L 5921:127.0.0.1:5921 maxw@192.168.100.55
/opt/TurboVNC/bin/vncviewer localhost::5921
```

---

## 5. 总结

| | 修复前 | 修复后 |
|---|---|---|
| VNC 服务 | x11vnc 0.9.16 | TurboVNC Xvnc 3.3 |
| 编码 | 单线程标准 Tight | 多线程优化 Tight + libjpeg-turbo |
| 帧更新延迟 | 40ms (defer+wait) | 1ms (deferupdate) |
| 变化检测 | 全屏轮询（-noxdamage） | 内建 framebuffer 脏区域追踪 |
| 桌面 | Xfce on Xorg :21 | Xfce on TurboVNC Xvnc :21 |
| GPU 应用 | 直接运行 | `vglrun -d :0` |
| 预期带宽/帧率 | 低 | ~10MBps / 高帧率 |

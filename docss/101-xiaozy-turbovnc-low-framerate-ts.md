# 101 - xiaozy TurboVNC 5922 低帧率排查与优化

日期：2026-06-30  
主机：5080-MS-eSport-Z890M / xiao-5080  
用户：xiaozy  
VNC：TurboVNC `:22` / TCP `5922`  
系统：Ubuntu 24.04  
GPU：NVIDIA GeForce RTX 5080

---

## 1. 结论先行

`5922` 当前已经是 TurboVNC Xvnc，不是 x11vnc，因此不是参考文档 `101-mx-turbovnc-low-framerate-ts.md` 里的 “x11vnc 导致低帧率” 问题。

当前低帧率更可能来自两类问题：

1. **VNC Viewer 端没有使用 TurboVNC 的 Tight/JPEG 快路径**  
   服务端日志显示多次连接都协商成了 `ZRLE`，并且像素格式是 `16 bpp`。这通常说明客户端不是 TurboVNC Viewer，或者 Viewer 参数/色深设置不理想。

2. **OpenGL/3D 应用没有通过 VirtualGL 使用 RTX 5080**  
   在 `DISPLAY=:22` 直接运行 OpenGL 会走 Mesa `llvmpipe` 软件渲染；使用 `vglrun -d :0` 后才会走 NVIDIA RTX 5080。

普通 Xfce 桌面卡顿，优先修 Viewer 编码和色深；MuJoCo、RViz、Gazebo、OpenGL 可视化程序卡顿，优先加 `vglrun -d :0`。

---

## 2. 当前状态证据

### 2.1 `5922` 是 TurboVNC Xvnc

```bash
ps -ef | grep "Xvnc :22" | grep -v grep
```

当前进程：

```text
/opt/TurboVNC/bin/Xvnc :22 \
  -geometry 1920x1080 \
  -depth 24 \
  -rfbport 5922 \
  -deferupdate 1 \
  -dridir /usr/lib/x86_64-linux-gnu/dri \
  -registrydir /usr/lib/xorg \
  -localhost
```

关键点：

- 已使用 TurboVNC `Xvnc`。
- 已使用 `-deferupdate 1`，更新延迟参数合理。
- 已使用 `-depth 24`，服务端色深合理。
- `-localhost` 合理，应通过 SSH tunnel 或 TurboVNC Viewer 内置 SSH tunnel 连接。

### 2.2 当前启动脚本

脚本：

```bash
/home/xiaozy/scripts/start-turbovnc-vnc22.sh
```

当前脚本核心参数是合理的：

```bash
/opt/TurboVNC/bin/vncserver :22 \
  -geometry 1920x1080 \
  -depth 24 \
  -deferupdate 1 \
  -dridir /usr/lib/x86_64-linux-gnu/dri \
  -registrydir /usr/lib/xorg \
  -localhost \
  -xstartup /home/xiaozy/.vnc/xstartup.turbovnc
```

### 2.3 服务端日志显示客户端协商异常

日志：

```bash
/home/xiaozy/.vnc/5080-MS-eSport-Z890M:22.log
```

多次连接都出现：

```text
Using ZRLE encoding
Using image quality level 6
Pixel format:
  16 bpp, depth 16
```

这不是 TurboVNC 连接高帧率场景下的理想状态。连接 TurboVNC Server 时，应优先使用 TurboVNC Viewer 的 `Tight` 编码，并启用 JPEG。`ZRLE` 是无损压缩，适合低色块/低变化画面，不适合高帧率桌面、视频、3D 或仿真画面。

---

## 3. GPU 加速判断

### 3.1 直接在 VNC Display 上运行 OpenGL

```bash
DISPLAY=:22 XAUTHORITY=/home/xiaozy/.Xauthority glxinfo -B
```

结果：

```text
OpenGL vendor string: Mesa
OpenGL renderer string: llvmpipe (LLVM 20.1.2, 256 bits)
Accelerated: no
```

含义：直接在 TurboVNC `:22` 里启动 OpenGL 程序时，默认是 CPU 软件渲染。

### 3.2 通过 VirtualGL 运行 OpenGL

```bash
DISPLAY=:22 XAUTHORITY=/home/xiaozy/.Xauthority vglrun -d :0 glxinfo -B
```

结果：

```text
OpenGL vendor string: NVIDIA Corporation
OpenGL renderer string: NVIDIA GeForce RTX 5080/PCIe/SSE2
OpenGL version string: 4.6.0 NVIDIA 580.126.20
```

含义：`vglrun -d :0` 可以把 OpenGL 渲染转发到物理 RTX 5080，再把结果显示回 TurboVNC。

---

## 4. 优化方案

### 4.1 客户端必须使用 TurboVNC Viewer

不要用系统自带 Remote Desktop、Remmina、TigerVNC Viewer、RealVNC Viewer、浏览器 VNC 插件等连接性能敏感的 TurboVNC 会话。

推荐在 Dell notebook 上使用 TurboVNC Viewer：

```bash
/opt/TurboVNC/bin/vncviewer \
  -Encoding Tight \
  -JPEG 1 \
  -Quality 80 \
  -Subsampling 1X \
  -CompressLevel 1 \
  localhost::5922
```

色深设置在 Viewer GUI 中确认：Options -> Color/Encoding 相关页面选择 Full Color 或 24-bit color，避免协商成日志里的 `16 bpp`。

如果先手动开 SSH tunnel：

```bash
ssh -N -L 5922:127.0.0.1:5922 xiao-5080
```

再运行上面的 `vncviewer localhost::5922`。

也可以使用 TurboVNC Viewer 自带 SSH tunnel 参数，避免单独开 tunnel：

```bash
/opt/TurboVNC/bin/vncviewer \
  -Tunnel \
  -Encoding Tight \
  -JPEG 1 \
  -Quality 80 \
  -Subsampling 1X \
  -CompressLevel 1 \
  xiao-5080:22
```

验证是否生效：连接后在远端查看日志。

```bash
grep -nE "Using (Tight|ZRLE)|Pixel format|image quality" \
  /home/xiaozy/.vnc/5080-MS-eSport-Z890M:22.log | tail -40
```

理想状态应看到 `Using Tight encoding`，并且不应再看到新的连接继续使用 `16 bpp`。

### 4.2 OpenGL/3D 程序用 VirtualGL 启动

在 VNC 终端中运行 OpenGL 程序时，不要直接运行：

```bash
./your_opengl_app
```

应使用：

```bash
vglrun -d :0 ./your_opengl_app
```

常见例子：

```bash
DISPLAY=:22 vglrun -d :0 glxgears
DISPLAY=:22 vglrun -d :0 glxinfo -B
DISPLAY=:22 vglrun -d :0 ./unitree_mujoco -i 0 -r g1 -s scene_29dof.xml
```

判断是否真的走 GPU：

```bash
nvidia-smi
```

同时在程序内或命令行确认：

```bash
vglrun -d :0 glxinfo -B | grep -E "OpenGL vendor|OpenGL renderer"
```

应输出：

```text
OpenGL vendor string: NVIDIA Corporation
OpenGL renderer string: NVIDIA GeForce RTX 5080/PCIe/SSE2
```

### 4.3 分辨率与画质参数

当前 `:22` 是 `1920x1080`，这是比较稳妥的默认值。若网络或客户端解码压力仍然较大，可以优先降低 Viewer 质量，而不是盲目改服务端：

低延迟优先：

```bash
/opt/TurboVNC/bin/vncviewer \
  -Encoding Tight -JPEG 1 -Quality 70 -Subsampling 2X -CompressLevel 1 \
  localhost::5922
```

画质优先：

```bash
/opt/TurboVNC/bin/vncviewer \
  -Encoding Tight -JPEG 1 -Quality 95 -Subsampling 1X -CompressLevel 1 \
  localhost::5922
```

如果要改服务端分辨率：

```bash
GEOMETRY=1600x900 /home/xiaozy/scripts/start-turbovnc-vnc22.sh
```

注意：该脚本会先停掉 xiaozy 自己的 `:22` Xvnc，再重新启动，因此会断开当前 VNC 会话。

### 4.4 服务端脚本可选增强

当前脚本已经可用。若要显式限制 TurboVNC Tight 编码线程，避免极端情况下抢占过多 CPU，可增加：

```bash
-nthreads 4
```

示例：

```bash
/opt/TurboVNC/bin/vncserver :22 \
  -geometry 1920x1080 \
  -depth 24 \
  -deferupdate 1 \
  -nthreads 4 \
  -dridir /usr/lib/x86_64-linux-gnu/dri \
  -registrydir /usr/lib/xorg \
  -localhost \
  -xstartup /home/xiaozy/.vnc/xstartup.turbovnc
```

这不是当前首要问题，因为日志显示瓶颈更像是客户端没有使用 Tight/JPEG，而不是服务端线程不足。

---

## 5. 推荐排查顺序

### Step 1：确认服务端仍是 TurboVNC

```bash
ps -ef | grep "Xvnc :22" | grep -v grep
ss -ltnp | grep 5922
```

期望：

```text
/opt/TurboVNC/bin/Xvnc :22 ... -rfbport 5922 ... -deferupdate 1
127.0.0.1:5922 LISTEN Xvnc
```

### Step 2：确认 Viewer 编码

连接后运行：

```bash
grep -nE "Using (Tight|ZRLE)|Pixel format" \
  /home/xiaozy/.vnc/5080-MS-eSport-Z890M:22.log | tail -30
```

判断：

| 日志 | 含义 | 处理 |
|---|---|---|
| `Using Tight encoding` | 正常 | 继续排查 GPU/应用 |
| `Using ZRLE encoding` | Viewer/参数不理想 | 换 TurboVNC Viewer，并指定 `-Encoding Tight` |
| `16 bpp, depth 16` | 客户端使用低色深 | 在 TurboVNC Viewer Options 里选择 Full Color/24-bit color；当前 CLI 帮助未暴露 FullColor 参数 |

### Step 3：确认 OpenGL 是否走 GPU

```bash
DISPLAY=:22 glxinfo -B | grep -E "OpenGL vendor|OpenGL renderer|Accelerated"
vglrun -d :0 glxinfo -B | grep -E "OpenGL vendor|OpenGL renderer"
```

判断：

| 结果 | 含义 |
|---|---|
| `Mesa llvmpipe`, `Accelerated: no` | 未用 GPU，CPU 软件渲染 |
| `NVIDIA GeForce RTX 5080` | 已用 GPU |

### Step 4：运行 3D 程序时加 `vglrun`

```bash
vglrun -d :0 <your_3d_app>
```

---

## 6. 与参考文档的差异

参考文档 `101-mx-turbovnc-low-framerate-ts.md` 的主问题是：端口实际跑的是 `x11vnc`，不是 TurboVNC Xvnc。

本次 `xiaozy:5922` 的状态不同：

| 项目 | 参考文档中的旧问题 | xiaozy 当前状态 |
|---|---|---|
| VNC 服务 | x11vnc | TurboVNC Xvnc |
| Display | 附着已有 Xorg | 独立 Xvnc `:22` |
| defer 参数 | x11vnc 默认等待较高 | `-deferupdate 1` |
| 服务端色深 | 取决于 Xorg/x11vnc | `-depth 24` |
| 主要异常 | 服务端架构错 | 客户端协商 `ZRLE`/`16 bpp`，OpenGL 默认 `llvmpipe` |
| OpenGL GPU | 需要 VirtualGL | 同样需要 `vglrun -d :0` |

---

## 7. 最小修复建议

优先按以下方式处理：

1. Dell notebook 上使用 TurboVNC Viewer，不使用通用 VNC Viewer。
2. 连接参数指定 `Tight + JPEG + Full Color/24-bit color`：

   ```bash
   /opt/TurboVNC/bin/vncviewer \
     -Encoding Tight -JPEG 1 -Quality 80 -Subsampling 1X -CompressLevel 1 \
     localhost::5922
   ```

   色深在 Viewer GUI 中确认选择 Full Color 或 24-bit color。

3. 在 VNC 中启动 OpenGL/3D 程序时加：

   ```bash
   vglrun -d :0 <app>
   ```

4. 连接后检查日志，确认不再出现新的 `Using ZRLE encoding`。


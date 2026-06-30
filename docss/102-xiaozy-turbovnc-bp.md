# xiaozy TurboVNC GPU 远程桌面最佳实践

> 编写日期：2026-06-30
> 编写者：基于 `100-sim-turnbovnc-bp-v2.md`（maxw/`:21`/5921）适配
>
> 主机：`5080-MS-eSport-Z890M` / `192.168.100.55`
> 用户：`xiaozy` (uid=1005，组 `users / docker / isaacusers / vglusers`)
> 分配资源：display `:22`，rfbport `5922`
>
> **与 maxw 的核心差异**
> - display `:21` / port 5921 已由 maxw 占用，xiaozy 使用 `:22` / 5922
> - xiaozy 不在 `sudo` 组 → 启动脚本不含 `sudo pkill`
> - xiaozy 不在 `video` / `render` 组，但已在 `vglusers` → VirtualGL 可用
> - `/run/user/1005` 已由 systemd-logind 创建，dbus/dconf 正常

---

## 0. TL;DR（懒人路径）

客户端：

```bash
ssh -N -L 5922:127.0.0.1:5922 xiaozy@192.168.100.55
```

主机端（以 xiaozy 身份，另一个 SSH 会话）：

```bash
~/scripts/start-turbovnc-vnc22.sh
```

客户端再开终端：

```bash
/opt/TurboVNC/bin/vncviewer localhost::5922
```

VNC 桌面里跑 GPU OpenGL 应用：

```bash
vglrun -d :0 <your-app>
```

---

## 1. 一次性初始化（首次配置，xiaozy 本人执行）

以 `xiaozy` 身份 SSH 登录主机后，执行以下命令完成所有初始化：

```bash
# 1. 创建目录
mkdir -p ~/.vnc ~/.config ~/.cache ~/scripts
chmod 700 ~/.vnc

# 2. 写入 xstartup.turbovnc
cat > ~/.vnc/xstartup.turbovnc << 'EOF'
#!/bin/sh
unset SESSION_MANAGER
unset DBUS_SESSION_BUS_ADDRESS
[ -n "${USER:-}" ] || export USER="$(id -un)"
[ -n "${LOGNAME:-}" ] || export LOGNAME="${USER}"
[ -n "${HOME:-}" ] || export HOME="$(getent passwd "${USER}" | cut -d: -f6)"
[ -n "${SHELL:-}" ] || export SHELL="/bin/bash"
export XDG_SESSION_TYPE=x11
export XDG_CURRENT_DESKTOP=XFCE
export DESKTOP_SESSION=xfce
export XDG_MENU_PREFIX=xfce-
export XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-${HOME}/.config}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-${HOME}/.cache}"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
case ":${XDG_CONFIG_DIRS:-}:" in
  *:/etc/xdg:*) ;;
  "::") export XDG_CONFIG_DIRS="/etc/xdg" ;;
  *) export XDG_CONFIG_DIRS="/etc/xdg:${XDG_CONFIG_DIRS}" ;;
esac
case ":${XDG_DATA_DIRS:-}:" in
  *:/usr/share:*) ;;
  "::") export XDG_DATA_DIRS="/usr/local/share:/usr/share" ;;
  *) export XDG_DATA_DIRS="${XDG_DATA_DIRS}:/usr/share" ;;
esac
mkdir -p "${HOME}" "${XDG_CONFIG_HOME}" "${XDG_CACHE_HOME}" "${XDG_RUNTIME_DIR}"
exec /usr/bin/dbus-run-session -- sh <<'EOS'
export XDG_SESSION_TYPE=x11
export XDG_CURRENT_DESKTOP=XFCE
export DESKTOP_SESSION=xfce
export XDG_MENU_PREFIX=xfce-
export XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-${HOME}/.config}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-${HOME}/.cache}"
export XDG_CONFIG_DIRS="${XDG_CONFIG_DIRS:-/etc/xdg}"
export XDG_DATA_DIRS="${XDG_DATA_DIRS:-/usr/local/share:/usr/share}"
mkdir -p "${XDG_CONFIG_HOME}" "${XDG_CACHE_HOME}"
xsetroot -solid "#1e2329"
/usr/lib/x86_64-linux-gnu/xfce4/xfconf/xfconfd &
/usr/bin/xfsettingsd &
/usr/bin/xfwm4 --replace &
/usr/bin/xfdesktop &
/usr/bin/xfce4-panel &
/usr/bin/thunar --daemon &
wait
EOS
EOF
chmod 755 ~/.vnc/xstartup.turbovnc

# 3. 写入启动脚本
cat > ~/scripts/start-turbovnc-vnc22.sh << 'EOF'
#!/usr/bin/env bash
set -euo pipefail
# xiaozy TurboVNC :22 (port 5922) — XFCE4 桌面
# 不使用 sudo；display :22 / port 5922 不与 maxw(:21/5921) 冲突

DISPLAY_NUM="${DISPLAY_NUM:-22}"
GEOMETRY="${GEOMETRY:-1920x1080}"
TURBOVNC="/opt/TurboVNC/bin"

# 清理上次残留（仅自己的进程，无需 sudo）
pkill -u xiaozy -f "Xvnc.*:${DISPLAY_NUM}" 2>/dev/null || true
sleep 1

"${TURBOVNC}/vncserver" ":${DISPLAY_NUM}" \
  -geometry "${GEOMETRY}" \
  -depth 24 \
  -deferupdate 1 \
  -dridir /usr/lib/x86_64-linux-gnu/dri \
  -registrydir /usr/lib/xorg \
  -localhost \
  -xstartup "${HOME}/.vnc/xstartup.turbovnc"

echo "TurboVNC :${DISPLAY_NUM} (port 59${DISPLAY_NUM}) ready."
echo "GPU apps: vglrun -d :0 <app>"
EOF
chmod 755 ~/scripts/start-turbovnc-vnc22.sh

# 4. 设置 VNC 密码（交互）
/opt/TurboVNC/bin/vncpasswd
```

---

## 2. 日常使用

### 2.1 启动桌面

```bash
ssh xiaozy@192.168.100.55   # 或用 SSH alias（见 §3）
~/scripts/start-turbovnc-vnc22.sh
```

### 2.2 状态检查

```bash
pgrep -af 'Xvnc.*:22'               # 应有 1 行
ss -tlnp 'sport = :5922'            # LISTEN 127.0.0.1:5922
pgrep -af 'xfwm4|xfce4-panel'       # ≥ 2 行
tail -n 30 ~/.vnc/$(hostname):22.log
```

### 2.3 停止

```bash
/opt/TurboVNC/bin/vncserver -kill :22
```

### 2.4 异常残留清理

```bash
pkill -u xiaozy -f 'Xvnc.*:22' || true
rm -f ~/.vnc/$(hostname):22.pid
rm -f /tmp/.X11-unix/X22 /tmp/.X22-lock
```

---

## 3. 客户端 SSH 配置（推荐）

在客户端 `~/.ssh/config` 里追加：

```sshconfig
Host g1host-xiaozy
    HostName 192.168.100.55
    User xiaozy
    IdentityFile ~/.ssh/id_ed25519
    ServerAliveInterval 30
    ServerAliveCountMax 3
    ControlMaster auto
    ControlPath ~/.ssh/cm-%r@%h:%p
    ControlPersist 10m
```

推送公钥（一次性）：

```bash
ssh-copy-id xiaozy@192.168.100.55
```

后续建立 tunnel：

```bash
ssh -N -L 5922:127.0.0.1:5922 g1host-xiaozy
```

---

## 4. VNC 连接

```bash
/opt/TurboVNC/bin/vncviewer localhost::5922
```

Viewer 调优参数（同 maxw v2 文档 §5.3）：

| 选项 | 推荐值 |
|------|--------|
| Encoding | Tight |
| Subsampling | 4:2:0（LAN）/ 4:4:4（视觉敏感） |
| Image quality | 80 |
| Compression | 1 或 2 |
| Continuous Updates | ✅ |

---

## 5. GPU 加速（VirtualGL）

xiaozy 已在 `vglusers` 组（gid=1010），可直接使用 `vglrun`。

```bash
vglrun -d :0 glxinfo | grep -E '^(server glx vendor|OpenGL (renderer|version)) '
# 期望：
#   server glx vendor string: VirtualGL
#   OpenGL renderer string  : NVIDIA GeForce RTX 5080/PCIe/SSE2
#   OpenGL version string   : 4.6.0 NVIDIA 580.126.20
```

**xhost 授权**：VirtualGL 转发到物理 Xorg `:0` 需要 xhost 许可。maxw 的 `~/.sim-env.sh` 会授权 `si:localuser:root`，但不会自动授权 `xiaozy`。在 VNC 桌面里首次用 `vglrun` 前，须先执行：

```bash
DISPLAY=:0 xhost +si:localuser:xiaozy
```

此命令需要以能访问 `:0` 的用户执行。方法一：请 maxw 执行一次并加入其 `~/.sim-env.sh`：

```bash
# 追加到 /home/maxw/.sim-env.sh（由 maxw 执行）
echo 'xhost +si:localuser:xiaozy >/dev/null 2>&1 || true' >> ~/.sim-env.sh
```

方法二：由 xiaozy 在 VNC 桌面的终端里临时执行（每次 Xorg :0 重启后重做）：

```bash
DISPLAY=:0 xhost +si:localuser:xiaozy   # 可能提示权限拒绝，取决于 xauth 配置
```

如仍报权限，请求 maxw 加入 `~/.sim-env.sh` 方法一是最可靠路径。

---

## 6. 容器化 GPU 应用

与 maxw 完全相同，display 改为 `:22`：

```bash
docker run --rm -it \
  --runtime nvidia --gpus all --net host \
  -e DISPLAY=:22 \
  -e XAUTHORITY=$HOME/.Xauthority \
  -e NVIDIA_DRIVER_CAPABILITIES=compute,utility,graphics \
  -e __NV_PRIME_RENDER_OFFLOAD=1 \
  -e __GLX_VENDOR_LIBRARY_NAME=nvidia \
  -v /tmp/.X11-unix:/tmp/.X11-unix:rw \
  -v $HOME/.Xauthority:$HOME/.Xauthority:ro \
  <image> bash
```

---

## 7. 资源隔离确认（防冲突）

| 资源 | maxw | xiaozy |
|------|------|--------|
| Display | `:21` | `:22` |
| rfbport | 5921 | 5922 |
| SSH tunnel 本地端口 | 5921 | 5922 |
| passwd 文件 | `~maxw/.vnc/passwd` | `~xiaozy/.vnc/passwd` |
| xstartup | `~maxw/.vnc/xstartup.turbovnc` | `~xiaozy/.vnc/xstartup.turbovnc` |
| log/pid | `~maxw/.vnc/$(host):21.*` | `~xiaozy/.vnc/$(host):22.*` |
| 启动脚本 | `~maxw/4sim/go2/scripts/start-go2-turbovnc-vnc21.sh` | `~xiaozy/scripts/start-turbovnc-vnc22.sh` |
| Xorg :0 (物理 GPU) | 共享（vglrun -d :0） | 共享（vglrun -d :0） |

两条 VNC 会话可同时运行，互不干扰。

---

## 8. 端到端验收清单

| # | 在哪里 | 命令 | 通过标准 |
|---|--------|------|----------|
| 1 | 客户端 | `ssh g1host-xiaozy 'echo ok'` | 立刻 `ok`，无密码 |
| 2 | 主机 | `pgrep -af 'Xvnc.*:22'` | 1 行 |
| 3 | 主机 | `ss -tlnp 'sport = :5922'` | LISTEN 127.0.0.1:5922 |
| 4 | 主机 | `pgrep -af 'xfwm4\|xfce4-panel'` | ≥ 2 行（xiaozy 的） |
| 5 | 客户端 | tunnel + `vncviewer localhost::5922` | 看到 XFCE4 桌面 |
| 6 | VNC 桌面终端 | `vglrun -d :0 glxinfo \| grep 'OpenGL renderer'` | `NVIDIA GeForce RTX 5080…` |
| 7 | VNC 桌面终端 | `vglrun -d :0 glxgears` | 窗口渲染正常 |

---

## 9. 故障排查

### vglrun 报 `Could not open display :0` / 权限拒绝

xiaozy 没有 xhost 授权到物理 `:0`。见 §5 的 xhost 授权步骤。

### `A VNC server is already running as :22`

```bash
pkill -u xiaozy -f 'Xvnc.*:22' || true
rm -f ~/.vnc/$(hostname):22.pid /tmp/.X11-unix/X22 /tmp/.X22-lock
```

### Viewer 连接成功但桌面灰屏

xstartup 没启动：

```bash
tail -50 ~/.vnc/$(hostname):22.log
# 常见：dbus-run-session 缺包
sudo apt install dbus-user-session xfce4 xfce4-goodies   # 需请管理员执行
```

### 5922 端口 LISTEN 但 Viewer 提示 Connection refused

检查客户端 tunnel 是否还活着：

```bash
ss -tlnp 'sport = :5922'    # 在客户端本地执行，确认 tunnel 建立
```

---

## 10. 安全基线

- Xvnc 绑定 `127.0.0.1:5922`（`-localhost`），LAN 不可直连
- 外部访问仅通过 SSH 22 + tunnel
- VNC 密码存 `~xiaozy/.vnc/passwd`（chmod 600，已由 vncpasswd 自动设置）
- 不要移除 `-localhost`，不要设置弱 VNC 密码

---

## 11. 引用

- `g1pilot/docss/100-sim-turnbovnc-bp-v2.md`：maxw`:21`/5921 配置权威文档（v2）
- `g1pilot/docss/100-sim-turnbovnc-bp.md`：v1 文档，Isaac Sim Xorg 路径

# dongxs / luyh TurboVNC GPU 远程桌面配置最佳实践

> 编写日期：2026-07-02
> 编写者：基于 `002-turbovnc_xiaozy_gpu_desktop_plan.md`、`102-xiaozy-turbovnc-bp.md`（xiaozy/`:22`/5922）适配
>
> 主机：`5080-MS-eSport-Z890M` / `192.168.100.55`
> 目标用户：`dongxs` (uid=1014)、`luyh` (uid=1015)
> 分配资源：
>
> | 用户 | display | rfbport |
> |------|---------|---------|
> | `dongxs` | `:23` | `5923` |
> | `luyh`   | `:24` | `5924` |

---

## 0. 前置结论（先说明白）

本文档遵循与 `xiaozy`/`maxw` 相同的行业最佳实践模式：**每个用户独立 display/port，VNC 只监听 `127.0.0.1`，客户端通过 SSH 隧道或 TurboVNC Session Manager 访问，GPU 加速走 VirtualGL + `vglusers` 组**。这是当前服务器已经跑通、且已有 4 个用户（`maxw:21`、`huanghb:19`、`xiaozy:22`，以及更早的 `100-*` 系列文档）验证过的方案，不引入新的架构或组件。

## 1. 当前实测环境核对（2026-07-02）

以 `xiaozy` 身份核对到的服务器现状：

- 主机名：`5080-MS-eSport-Z890M`，`192.168.100.55`
- 系统：Ubuntu 24.04.2 LTS，内核 `6.17.0-35-generic`
- GPU：`NVIDIA GeForce RTX 5080`
- TurboVNC：`/opt/TurboVNC/bin/vncserver` 已安装
- VirtualGL：`/opt/VirtualGL/bin/vglrun` 已安装
- `/etc/turbovncserver-security.conf`：

  ```text
  no-remote-connections
  no-reverse-connections
  ```

  即服务器级策略强制 VNC 只能本机监听，不允许远程直连或反向连接。这一策略对所有用户生效，**不需要也不应该为新用户单独修改**。

- 当前已占用的 TurboVNC display/port：

  | 用户 | display | port |
  |------|---------|------|
  | `huanghb` | `:19` | `5919` |
  | `maxw` | `:21` | `5921` |
  | `xiaozy` | `:22` | `5922` |

  `:20`、`:23`、`:24` 等均未被占用（无对应 `/tmp/.X*-lock`，无监听端口）。为避免未来冲突并延续既有编号习惯，本文给：

  - `dongxs` 分配 `:23` / `5923`
  - `luyh` 分配 `:24` / `5924`

- 系统账号现状：`dongxs` (uid=1014)、`luyh` (uid=1015) 已经存在系统账号和 `/home` 目录，主组分别是 `dongxs`、`luyh`，均在 `users`、`docker`、`isaacusers` 组，但**均不在 `vglusers` 组**——这是当前二人无法使用 GPU 加速的唯一缺口。
- `vglusers` 组当前成员：`maxw,liangfx,hongzt,aitech,huanghb,xiaozy,zhangzh,tongyq`（不含 dongxs、luyh）。
- 以 `xiaozy` 身份没有 sudo 权限（`sudo -n true` 失败），因此涉及加组、开 linger 的步骤需要**服务器管理员**（有 sudo 权限的人）执行；剩余的用户级配置由 `dongxs`、`luyh` 本人以自己的账号执行。

## 2. 总体方案

沿用 `xiaozy`（`102-xiaozy-turbovnc-bp.md`）的方案，两位新用户各自独立：

- 独立 TurboVNC display 和 TCP 端口（`dongxs :23/5923`，`luyh :24/5924`），避免与已存在的 `huanghb:19`、`maxw:21`、`xiaozy:22` 冲突。
- 独立 `~/.vnc/passwd`、`~/.vnc/xstartup.turbovnc`、启动脚本，互不共享、互不覆盖。
- VNC server 只监听 `127.0.0.1`（`-localhost`），符合服务器安全基线，不需要也不应该对外开放监听。
- 桌面环境统一用 Xfce（`xfce4` + `xfce4-session`，服务器已安装，无需重复安装）。
- GPU 加速通过 VirtualGL：`vglrun -d :0 <程序>`，前提是用户加入 `vglusers` 组。
- 客户端访问方式：优先 TurboVNC Viewer 的 Session Manager（自动 SSH 隧道），备用手动 `ssh -L` 隧道 + VNC Viewer。

## 3. 需要管理员执行的步骤（一次性，仅 2 条命令）

以下命令**必须由具有 sudo 权限的管理员执行一次**，`dongxs`、`luyh` 或 `xiaozy` 自己都无法完成：

```bash
sudo usermod -aG vglusers dongxs
sudo usermod -aG vglusers luyh
```

执行后，`dongxs`、`luyh` 需要**完全退出**当前所有 SSH/桌面会话，重新登录才能让新组生效（Linux 组成员变更不会影响已存在的登录 session）。

可选（建议）：为支持"退出 SSH 后 VNC 仍在后台运行"和 systemd `--user` 服务方式，管理员可顺带开启 linger（参考 `xiaozy` 已是 `Linger=yes`）：

```bash
sudo loginctl enable-linger dongxs
sudo loginctl enable-linger luyh
```

不开启 linger 的影响：`dongxs`/`luyh` 退出所有 SSH 会话后，其用户级 systemd 服务和后台进程（包括 VNC）会被 systemd-logind 结束。如果两人只是"登录着用，用完就 kill VNC 再退出"，可以不开启；但如果希望"VNC 一直挂在后台，随用随连"，则必须开启。本文第 8 节的自启动方案依赖 linger。

无需管理员操作的部分：

- `/etc/turbovncserver-security.conf` 已经是 `no-remote-connections` + `no-reverse-connections`，对所有用户统一生效，不需要改动。
- TurboVNC、VirtualGL、Xfce、`dbus-x11`、`xauth` 等软件包已经全局安装，不需要重复安装。
- `/etc/X11/xorg.conf.d/99-virtualgl-dri.conf` 和 `/etc/lightdm/lightdm.conf.d/99-virtualgl.conf` 是全局 GPU 授权配置，已经存在，不需要改动。

## 4. dongxs 用户配置步骤（dongxs 本人执行）

管理员完成第 3 节的 `usermod` 并且 `dongxs` 已重新登录后，执行：

```bash
ssh xiao-5080   # 或 ssh dongxs@192.168.100.55
```

确认组生效：

```bash
id
groups
```

期望看到 `dongxs` 已包含 `vglusers`。如果没有，说明还没有完全退出重新登录，先退出所有会话再重试。

创建 VNC 目录：

```bash
mkdir -p ~/.vnc ~/scripts
chmod 700 ~/.vnc
```

设置 VNC 密码（**不要复用他人密码，不要向任何人发送/粘贴密码文件内容**）：

```bash
/opt/TurboVNC/bin/vncpasswd
```

写入 xstartup 脚本（与 `xiaozy` 保持同一套经过验证的 Xfce 启动方式）：

```bash
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
/usr/lib/x86_64-linux-gnu/xfce4/xfconfd &
/usr/bin/xfsettingsd &
/usr/bin/xfwm4 --replace &
/usr/bin/xfdesktop &
/usr/bin/xfce4-panel &
/usr/bin/thunar --daemon &
wait
EOS
EOF
chmod 755 ~/.vnc/xstartup.turbovnc
```

写入启动脚本（display `:23`，port `5923`）：

```bash
cat > ~/scripts/start-turbovnc-vnc23.sh << 'EOF'
#!/usr/bin/env bash
set -euo pipefail
# dongxs TurboVNC :23 (port 5923) — XFCE4 桌面
# 不使用 sudo；display :23 / port 5923 不与 huanghb(:19)/maxw(:21)/xiaozy(:22) 冲突

DISPLAY_NUM="${DISPLAY_NUM:-23}"
GEOMETRY="${GEOMETRY:-1920x1080}"
TURBOVNC="/opt/TurboVNC/bin"

pkill -u dongxs -f "Xvnc.*:${DISPLAY_NUM}" 2>/dev/null || true
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
chmod 755 ~/scripts/start-turbovnc-vnc23.sh
```

启动桌面：

```bash
~/scripts/start-turbovnc-vnc23.sh
```

## 5. luyh 用户配置步骤（luyh 本人执行）

与第 4 节完全一致，仅把 `:23`/`5923`/`dongxs` 替换为 `:24`/`5924`/`luyh`：

```bash
ssh xiao-5080   # 或 ssh luyh@192.168.100.55

id
groups   # 确认包含 vglusers

mkdir -p ~/.vnc ~/scripts
chmod 700 ~/.vnc

/opt/TurboVNC/bin/vncpasswd
```

xstartup 脚本内容与第 4 节完全相同（可直接复制）：

```bash
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
/usr/lib/x86_64-linux-gnu/xfce4/xfconfd &
/usr/bin/xfsettingsd &
/usr/bin/xfwm4 --replace &
/usr/bin/xfdesktop &
/usr/bin/xfce4-panel &
/usr/bin/thunar --daemon &
wait
EOS
EOF
chmod 755 ~/.vnc/xstartup.turbovnc
```

启动脚本（display `:24`，port `5924`）：

```bash
cat > ~/scripts/start-turbovnc-vnc24.sh << 'EOF'
#!/usr/bin/env bash
set -euo pipefail
# luyh TurboVNC :24 (port 5924) — XFCE4 桌面
# 不使用 sudo；display :24 / port 5924 不与 huanghb(:19)/maxw(:21)/xiaozy(:22)/dongxs(:23) 冲突

DISPLAY_NUM="${DISPLAY_NUM:-24}"
GEOMETRY="${GEOMETRY:-1920x1080}"
TURBOVNC="/opt/TurboVNC/bin"

pkill -u luyh -f "Xvnc.*:${DISPLAY_NUM}" 2>/dev/null || true
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
chmod 755 ~/scripts/start-turbovnc-vnc24.sh
```

启动桌面：

```bash
~/scripts/start-turbovnc-vnc24.sh
```

## 6. 启动后验证（两人各自在自己账号下执行）

以 `dongxs` 为例（`luyh` 把 `23`/`5923`/`dongxs` 换成 `24`/`5924`/`luyh` 即可）：

```bash
/opt/TurboVNC/bin/vncserver -list          # 期望看到 :23
pgrep -af 'Xvnc.*:23'                      # 应有 1 行
ss -ltn | grep 5923                        # 期望 127.0.0.1:5923
pgrep -af 'xfwm4|xfce4-panel'               # 应 ≥ 2 行
tail -n 60 ~/.vnc/$(hostname):23.log
```

常见问题排查（与 `xiaozy`/`maxw` 文档一致）：

- `The session desktop file ... was not found`：xstartup 权限或路径问题，确认 `chmod 755 ~/.vnc/xstartup.turbovnc`。
- `Password too short`：重新执行 `/opt/TurboVNC/bin/vncpasswd`。
- `A VNC server is already running as :23`：清理残留，见第 9 节。
- Xfce/DBus 报错：确认 `dbus-x11`、`xfce4-session` 已安装（服务器已全局安装，通常无需处理）。

## 7. 客户端连接方式

### 7.1 推荐：TurboVNC Viewer Session Manager

```bash
/Applications/TurboVNC\ Viewer.app/Contents/MacOS/vncviewer dongxs@xiao-5080
```

或（luyh）：

```bash
/Applications/TurboVNC\ Viewer.app/Contents/MacOS/vncviewer luyh@xiao-5080
```

Session Manager 会通过 SSH 自动发现并连接远端 TurboVNC 会话，自动建立隧道，无需手动指定端口。前提是客户端能以 `dongxs`/`luyh` 身份 SSH 到服务器（建议配置 SSH key 免密登录，见下）。

### 7.2 备用：手动 SSH 隧道 + VNC Viewer

`dongxs`（端口 5923）：

```bash
ssh -N -L 5923:127.0.0.1:5923 dongxs@192.168.100.55
```

`luyh`（端口 5924）：

```bash
ssh -N -L 5924:127.0.0.1:5924 luyh@192.168.100.55
```

保持隧道终端不关闭，另开终端连接：

```bash
/opt/TurboVNC/bin/vncviewer localhost::5923   # dongxs
/opt/TurboVNC/bin/vncviewer localhost::5924   # luyh
```

由于服务器只监听 `127.0.0.1`，直接从客户端连 `xiao-5080:5923`/`5924` 会失败，这是安全策略下的正常行为，不需要也不应该尝试让 VNC 端口对外监听。

### 7.3 客户端 SSH 免密登录配置（可选但推荐）

客户端 `~/.ssh/config` 追加（以 dongxs 为例，luyh 类似）：

```sshconfig
Host g1host-dongxs
    HostName 192.168.100.55
    User dongxs
    IdentityFile ~/.ssh/id_ed25519
    ServerAliveInterval 30
    ServerAliveCountMax 3
    ControlMaster auto
    ControlPath ~/.ssh/cm-%r@%h:%p
    ControlPersist 10m
```

推送公钥（在客户端执行，需要输入一次密码）：

```bash
ssh-copy-id dongxs@192.168.100.55
```

## 8. Viewer 参数调优（与既有文档一致）

| 选项 | 推荐值 |
|------|--------|
| Encoding | Tight |
| Subsampling | 4:2:0（LAN）/ 4:4:4（视觉敏感场景） |
| Image quality | 80 |
| Compression | 1 或 2 |
| Continuous Updates | ✅ |

## 9. GPU 加速验证（VirtualGL）

前提：`dongxs`/`luyh` 已被管理员加入 `vglusers`，并已重新登录使组生效。

```bash
id   # 确认包含 vglusers
vglrun -d :0 glxinfo | grep -E '^(server glx vendor|OpenGL (renderer|version)) '
```

期望输出：

```text
server glx vendor string: VirtualGL
OpenGL renderer string  : NVIDIA GeForce RTX 5080/PCIe/SSE2
OpenGL version string   : 4.6.0 NVIDIA 580.126.20
```

进一步测试：

```bash
vglrun -d :0 /opt/VirtualGL/bin/glxspheres64
```

若报 `Could not open display :0` 或权限拒绝，说明当前登录会话的组信息还没刷新，需完全退出所有 SSH/VNC 会话后重新登录；如果重新登录后仍报权限错误，很可能是物理 `:0` Xorg 的 `xhost` 授权问题——这属于服务器级的 `vglusers` 组 + `99-virtualgl-dri.conf` 授权机制，`dongxs`/`luyh` 加入 `vglusers` 组后通常会自动继承 GPU 设备访问权限，不需要像旧版文档中单独 `xhost +si:localuser:<user>`（该做法针对更早期的、未把用户加入 `vglusers` 的场景）。若验证后仍无法访问，请联系管理员核实 `/dev/nvidia*`、`/dev/dri/renderD128` 的属组是否为 `vglusers`。

容器化 GPU 应用（如需要）：

```bash
docker run --rm -it \
  --runtime nvidia --gpus all --net host \
  -e DISPLAY=:23 \
  -e XAUTHORITY=$HOME/.Xauthority \
  -e NVIDIA_DRIVER_CAPABILITIES=compute,utility,graphics \
  -e __NV_PRIME_RENDER_OFFLOAD=1 \
  -e __GLX_VENDOR_LIBRARY_NAME=nvidia \
  -v /tmp/.X11-unix:/tmp/.X11-unix:rw \
  -v $HOME/.Xauthority:$HOME/.Xauthority:ro \
  <image> bash
```

（`luyh` 把 `DISPLAY=:23` 换成 `:24`。）

## 10. 日常操作

启动：

```bash
~/scripts/start-turbovnc-vnc23.sh   # dongxs
~/scripts/start-turbovnc-vnc24.sh   # luyh
```

停止：

```bash
/opt/TurboVNC/bin/vncserver -kill :23   # dongxs
/opt/TurboVNC/bin/vncserver -kill :24   # luyh
```

重启：

```bash
/opt/TurboVNC/bin/vncserver -kill :23 && ~/scripts/start-turbovnc-vnc23.sh
```

异常残留清理（仅清理自己的 display，不要动别人的锁文件/进程）：

```bash
pkill -u dongxs -f 'Xvnc.*:23' || true
rm -f ~/.vnc/$(hostname):23.pid
rm -f /tmp/.X11-unix/X23 /tmp/.X23-lock
```

## 11. 可选：登录后自动启动（systemd --user，依赖 linger）

前提：管理员已执行 `sudo loginctl enable-linger dongxs`（或 `luyh`）。

以 `dongxs` 为例：

```bash
mkdir -p ~/.config/systemd/user

cat > ~/.config/systemd/user/turbovnc-23.service <<'EOF'
[Unit]
Description=TurboVNC display :23 for dongxs
After=default.target

[Service]
Type=forking
PIDFile=/home/dongxs/.vnc/5080-MS-eSport-Z890M:23.pid
ExecStart=/opt/TurboVNC/bin/vncserver -geometry 1920x1080 -depth 24 -localhost -xstartup /home/dongxs/.vnc/xstartup.turbovnc :23
ExecStop=/opt/TurboVNC/bin/vncserver -kill :23
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now turbovnc-23.service
systemctl --user status turbovnc-23.service --no-pager -l
```

`luyh` 把上面所有 `23`/`dongxs` 替换为 `24`/`luyh` 即可。

如果服务器 hostname 变化，需要同步更新 `PIDFile` 中的 `5080-MS-eSport-Z890M`。

不开启 linger 也完全可用，只是需要 `dongxs`/`luyh` 每次要用桌面时手动执行启动脚本，SSH 会话退出后 VNC 进程也会随之结束（除非另有 `nohup`/`disown`，但不推荐绕过 linger 机制手工 hack）。

## 12. 资源隔离一览表

| 资源 | huanghb | maxw | xiaozy | **dongxs（新增）** | **luyh（新增）** |
|------|---------|------|--------|------|------|
| Display | `:19` | `:21` | `:22` | `:23` | `:24` |
| rfbport | 5919 | 5921 | 5922 | **5923** | **5924** |
| SSH tunnel 本地端口 | 5919 | 5921 | 5922 | **5923** | **5924** |
| passwd 文件 | `~huanghb/.vnc/passwd` | `~maxw/.vnc/passwd` | `~xiaozy/.vnc/passwd` | `~dongxs/.vnc/passwd` | `~luyh/.vnc/passwd` |
| xstartup | 各自 `~/.vnc/xstartup.turbovnc` | 同 | 同 | 同 | 同 |
| 启动脚本 | - | - | `~xiaozy/scripts/start-turbovnc-vnc22.sh` | `~dongxs/scripts/start-turbovnc-vnc23.sh` | `~luyh/scripts/start-turbovnc-vnc24.sh` |
| Xorg :0（物理 GPU） | 共享（vglrun -d :0） | 共享 | 共享 | 共享 | 共享 |

五条 VNC 会话可同时运行，互不干扰，物理 GPU `:0` 由所有 `vglusers` 组成员共享访问。

## 13. 端到端验收清单

| # | 在哪里 | 命令（以 dongxs 为例） | 通过标准 |
|---|--------|------|----------|
| 1 | 管理员 | `getent group vglusers` | 输出包含 `dongxs`、`luyh` |
| 2 | dongxs 客户端 | `ssh dongxs@192.168.100.55 'id'` | groups 含 `vglusers` |
| 3 | 主机（dongxs 身份） | `pgrep -af 'Xvnc.*:23'` | 1 行 |
| 4 | 主机 | `ss -ltn \| grep 5923` | `127.0.0.1:5923` |
| 5 | 主机 | `pgrep -af 'xfwm4\|xfce4-panel'`（dongxs 会话内） | ≥ 2 行 |
| 6 | 客户端 | tunnel + `vncviewer localhost::5923` | 看到 XFCE4 桌面 |
| 7 | VNC 桌面终端 | `vglrun -d :0 glxinfo \| grep 'OpenGL renderer'` | `NVIDIA GeForce RTX 5080…` |
| 8 | VNC 桌面终端 | `vglrun -d :0 glxgears` | 窗口渲染正常 |

`luyh` 同样流程，display/port 换成 `:24`/`5924`。

## 14. 安全基线（不要破坏）

- Xvnc 必须保留 `-localhost`，绑定 `127.0.0.1`，LAN 不可直连，这是当前服务器 `/etc/turbovncserver-security.conf` 的强制策略，任何用户都不应尝试绕过。
- 外部访问只能通过 SSH + 隧道，或 TurboVNC Session Manager。
- 每个用户的 VNC 密码文件（`~/.vnc/passwd`）权限保持 `600`，不共享、不外发。
- 不要把 GPU 设备节点（`/dev/nvidia*`）或 `/etc/X11/xorg.conf.d/99-virtualgl-dri.conf` 权限放宽到超出 `vglusers` 组的范围。
- 新增用户加组操作（`usermod -aG vglusers`）只应由拥有 sudo 的管理员执行并记录，不应绕过审批自行提权。

## 15. 引用

- `002-turbovnc_xiaozy_gpu_desktop_plan.md`：xiaozy 首次配置规划文档，包含服务器基础环境核对方法。
- `102-xiaozy-turbovnc-bp.md`：xiaozy（`:22`/5922）最佳实践文档，本方案的直接模板来源。

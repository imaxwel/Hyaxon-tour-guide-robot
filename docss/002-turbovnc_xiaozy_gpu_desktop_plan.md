# xiaozy TurboVNC GPU 虚拟桌面配置步骤

本文用于在 RTX 5080 服务器 `xiao-5080` 上，为当前 `xiaozy` 用户配置一个可由 MacBook Pro 上的 TurboVNC Viewer 访问的 GPU 加速虚拟桌面。步骤参考了当前服务器实际状态，以及当前能从 `xiaozy` 身份看到的 `maxw` TurboVNC 会话。

## 1. 当前实测环境

实测时间：2026-06-30。

服务器：

- SSH 入口：`ssh xiao-5080`
- SSH 配置解析：`xiaozy@192.168.100.55:22`
- 主机名：`5080-MS-eSport-Z890M`
- 系统：Ubuntu 24.04.2 LTS
- 内核：`6.17.0-35-generic`
- GPU：`NVIDIA GeForce RTX 5080`
- NVIDIA 驱动：`580.126.20`
- GPU 显存：`16303 MiB`

当前用户：

- 用户：`xiaozy`
- HOME：`/home/xiaozy`
- 组：`xiaozy users docker isaacusers vglusers`
- `xiaozy` 已在 `vglusers`，这是当前 VirtualGL/Xorg 访问 GPU 所需的关键组。
- 当前没有免密 sudo：`sudo -n true` 返回失败，因此本文默认只使用用户级配置。

已安装的关键组件：

- TurboVNC：`turbovnc 3.3-20260206`
- TurboVNC Server：`/opt/TurboVNC/bin/vncserver`
- TurboVNC Xvnc：`/opt/TurboVNC/bin/Xvnc`
- VirtualGL：`virtualgl 3.1.4-20251007`
- VirtualGL 命令：`/opt/VirtualGL/bin/vglrun`，同时 `/usr/bin/vglrun` 也存在
- 桌面环境：Xfce 已安装，`xfce4 4.18`，`xfce4-session 4.18.3`
- `dbus-x11`、`xauth`、`mesa-utils`、`xfonts-base` 已安装

图形和 VirtualGL 系统配置：

- `lightdm.service` 正在运行。
- 物理 Xorg 运行在 `:0`。
- `/etc/X11/xorg.conf.d/99-virtualgl-dri.conf`：

```conf
Section "DRI"
        Mode 0660
        Group "vglusers"
EndSection
```

- `/etc/lightdm/lightdm.conf.d/99-virtualgl.conf` 配置了：

```ini
[Seat:seat*]
greeter-setup-script=/opt/VirtualGL/bin/vglgenkey
```

- GPU 设备当前归属允许 `vglusers` 使用，例如 `/dev/nvidia0`、`/dev/nvidiactl`、`/dev/dri/renderD128` 的组为 `vglusers`。

TurboVNC 安全策略：

- `/etc/turbovncserver-security.conf` 内容为：

```text
no-remote-connections
no-reverse-connections
```

因此当前服务器策略是不允许 VNC 端口直接对局域网开放。TurboVNC 会话会监听 `127.0.0.1`，客户端应通过 SSH 隧道或 TurboVNC Viewer 的 Session Manager 连接。

MacBook Pro 客户端状态：

- 当前检测到 `/Applications/VNC Viewer.app/Contents/MacOS/vncviewer`。
- 该应用是 RealVNC，`CFBundleIdentifier` 为 `com.realvnc.vncviewer`，版本 `7.12.1`，不是 TurboVNC Viewer。
- RealVNC 可作为手动 SSH 隧道后的普通 VNC 客户端备用，但不支持 TurboVNC Session Manager。建议安装并使用 TurboVNC Viewer。

## 2. 当前可见的 maxw 参考状态

`xiaozy` 不能读取 `/home/maxw/.vnc`，因为 `/home/maxw` 权限是 `drwxr-x---`。但进程和端口信息可见：

- `maxw` 正在运行 TurboVNC 会话 `:21`。
- VNC 端口是 `5921`。
- 只监听 `127.0.0.1:5921`。
- 分辨率：`1920x1080`
- 色深：`24`
- 启动脚本：`/home/maxw/.vnc/xstartup.turbovnc`
- 日志：`/home/maxw/.vnc/5080-MS-eSport-Z890M:21.log`
- Xfce 相关进程正在运行，例如 `xfce4-panel`、`xfce4-notifyd`。

当前可见的 `maxw` Xvnc 关键参数：

```text
/opt/TurboVNC/bin/Xvnc :21
-desktop "TurboVNC: 5080-MS-eSport-Z890M:21 (maxw)"
-auth /home/maxw/.Xauthority
-geometry 1920x1080
-depth 24
-rfbauth /home/maxw/.vnc/passwd
-x509cert /home/maxw/.vnc/x509_cert.pem
-x509key /home/maxw/.vnc/x509_private.pem
-rfbport 5921
-localhost
```

这个状态说明：`xiaozy` 推荐复用同样的桌面类型和连接模式，但不要复制 `maxw` 的 `passwd`、证书或私有配置文件。

## 3. 推荐目标方案

为避免和 `maxw` 的 `:21`/`5921` 冲突，建议给 `xiaozy` 固定使用：

- TurboVNC display：`:22`
- TCP 端口：`5922`
- 监听地址：`127.0.0.1`
- 桌面环境：Xfce
- 分辨率：`1920x1080`
- 色深：`24`
- GPU 加速方式：TurboVNC `-vgl` 加 VirtualGL；3D 程序优先用 `vglrun -d :0 <程序>` 启动验证。

当前服务器未发现 `/tmp/.X22-lock`，也未发现 `5922` 监听，因此 `:22` 是合理选择。如果后续被占用，改用 `:23`，对应端口 `5923`。

## 4. xiaozy 用户配置步骤

登录服务器：

```bash
ssh xiao-5080
```

确认当前身份和关键组：

```bash
id
groups
```

期望能看到 `xiaozy` 和 `vglusers`。如果没有 `vglusers`，需要管理员执行：

```bash
sudo usermod -aG vglusers xiaozy
```

然后 `xiaozy` 需要完全退出服务器登录会话，再重新登录。

创建 TurboVNC 用户目录：

```bash
mkdir -p ~/.vnc
chmod 700 ~/.vnc
```

设置 `xiaozy` 自己的 VNC 密码：

```bash
/opt/TurboVNC/bin/vncpasswd
```

注意：

- 不要复制 `maxw` 的 `~/.vnc/passwd`。
- TurboVNC 会拒绝太短的密码。
- `~/.vnc/passwd` 是敏感文件，不要发送给别人，不要粘贴其内容。

建议写入用户级 TurboVNC 默认配置：

```bash
cat > ~/.vnc/turbovncserver.conf <<'EOF'
$geometry = "1920x1080";
$depth = 24;
$wm = "xfce";
$useVGL = 1;
$serverArgs = "-localhost";
EOF

chmod 600 ~/.vnc/turbovncserver.conf
```

说明：

- `$wm = "xfce"` 会使用 `/usr/share/xsessions/xfce.desktop`。
- `$useVGL = 1` 等价于启动时加 `-vgl`，TurboVNC 默认会用 `vglrun +wm` 启动窗口管理器。
- `$serverArgs = "-localhost"` 明确只监听本机。当前系统安全策略本身也会强制本机监听。

启动 `:22` 会话：

```bash
/opt/TurboVNC/bin/vncserver :22
```

也可以不用配置文件，直接用完整命令启动：

```bash
/opt/TurboVNC/bin/vncserver -geometry 1920x1080 -depth 24 -wm xfce -vgl -localhost :22
```

二选一即可。推荐使用配置文件后执行短命令，便于后续重启保持一致。

## 5. 启动后验证

查看 `xiaozy` 的 TurboVNC 会话：

```bash
/opt/TurboVNC/bin/vncserver -list
```

期望看到 `:22`。

检查端口监听：

```bash
ss -ltn | awk 'NR == 1 || /127\.0\.0\.1:5922/'
```

期望看到 `127.0.0.1:5922`。如果只看到 `127.0.0.1`，这是正确的，因为当前服务器禁止远程直连 VNC。

查看进程：

```bash
ps -fu "$USER" | grep -E 'Xvnc|xfce|vncserver' | grep -v grep
```

查看日志：

```bash
tail -n 160 ~/.vnc/$(hostname):22.log
```

如果启动失败，优先看日志中是否有：

- `The session desktop file ... was not found`：通常是 `-wm` 写错或桌面环境缺失。
- `Password too short`：VNC 密码太短，重新运行 `vncpasswd`。
- `A VNC server is already running as :22`：display 已被占用，换成 `:23`。
- Xfce/DBus 相关错误：确认 `dbus-x11`、`xfce4-session` 存在。当前服务器已经安装。

## 6. MacBook Pro 连接方式

### 6.1 推荐：TurboVNC Viewer Session Manager

安装 TurboVNC Viewer 后，优先使用 TurboVNC 自带的 Session Manager，因为它能通过 SSH 自动列出或连接远端 TurboVNC 会话，并自动处理隧道。

命令行方式通常类似：

```bash
/Applications/TurboVNC\ Viewer.app/Contents/MacOS/vncviewer xiaozy@xiao-5080
```

如果安装路径不同，先查找：

```bash
find /Applications -maxdepth 4 -iname '*TurboVNC*' -print
```

连接时选择 `xiaozy` 的 `:22` 会话。由于本机 SSH 配置已经能 `ssh xiao-5080` 免密登录，Session Manager 通常可以直接复用。

### 6.2 备用：手动 SSH 隧道加 VNC Viewer

如果暂时只有 RealVNC Viewer，可以先在 Mac 上开一个 SSH 隧道：

```bash
ssh -N -L 5922:localhost:5922 xiao-5080
```

保持该终端窗口不关闭，然后在 VNC Viewer 中连接：

```text
localhost:5922
```

或在 TurboVNC Viewer 中连接：

```text
localhost::5922
```

说明：

- `5922` 是 `:22` 对应的 TCP 端口。
- 由于服务器只监听 `127.0.0.1:5922`，从 Mac 直接连接 `xiao-5080:5922` 预计会失败，这是当前安全策略下的正常行为。
- 手动隧道模式下，如果改用 `:23`，则端口也要改成 `5923`。

## 7. GPU 加速验证

进入 VNC 桌面后打开终端，先确认当前 VNC display：

```bash
echo "$DISPLAY"
```

期望类似：

```text
:22
```

普通 OpenGL 信息：

```bash
glxinfo -B | egrep 'direct rendering|OpenGL vendor|OpenGL renderer|OpenGL version'
```

VirtualGL GPU 渲染验证：

```bash
vglrun -d :0 glxinfo -B | egrep 'direct rendering|OpenGL vendor|OpenGL renderer|OpenGL version'
```

期望在 `vglrun -d :0` 的输出中看到 NVIDIA 相关 renderer，例如 `NVIDIA GeForce RTX 5080`。如果普通 `glxinfo -B` 显示 Mesa、llvmpipe 或 TurboVNC 相关 renderer，不一定代表失败；关键是 3D 程序通过 `vglrun -d :0` 能走 NVIDIA。

进一步测试：

```bash
vglrun -d :0 /opt/VirtualGL/bin/glxspheres64
```

另开一个 SSH 终端观察 GPU：

```bash
ssh xiao-5080
nvidia-smi
```

运行 `glxspheres64` 时，`nvidia-smi` 中应能看到相关进程或 GPU 利用率变化。

也可以不进入桌面，直接从 SSH 验证已启动的 `:22` VNC display：

```bash
DISPLAY=:22 vglrun -d :0 glxinfo -B | egrep 'OpenGL vendor|OpenGL renderer|OpenGL version'
```

注意：如果在纯 SSH 环境里直接运行 `vglrun glxinfo -B`，VirtualGL 可能会尝试把 DISPLAY 自动设到 SSH 客户端地址，导致 `unable to open display`。因此需要显式指定 `DISPLAY=:22`，并用 `-d :0` 指向物理 GPU Xorg。

## 8. 日常操作

列出当前会话：

```bash
/opt/TurboVNC/bin/vncserver -list
```

停止 `:22`：

```bash
/opt/TurboVNC/bin/vncserver -kill :22
```

重启 `:22`：

```bash
/opt/TurboVNC/bin/vncserver -kill :22
/opt/TurboVNC/bin/vncserver :22
```

如果 `:22` 卡住或异常退出，先确认没有残留进程：

```bash
ps -fu "$USER" | grep -E 'Xvnc|xfce|vncserver' | grep -v grep
```

只有在确认没有 `xiaozy` 的 `:22` 进程后，才考虑清理 `xiaozy` 自己的残留锁文件。不要删除其他用户的 `/tmp/.X*-lock`：

```bash
ls -l /tmp/.X22-lock /tmp/.X11-unix/X22 2>/dev/null
```

## 9. 可选：开机或登录后自动启动

当前 `loginctl show-user xiaozy -p Linger` 显示 `Linger=yes`，因此 `xiaozy` 可以使用用户级 systemd 服务保持后台会话。

先确保已经执行过：

```bash
/opt/TurboVNC/bin/vncpasswd
```

创建用户服务：

```bash
mkdir -p ~/.config/systemd/user

cat > ~/.config/systemd/user/turbovnc-22.service <<'EOF'
[Unit]
Description=TurboVNC display :22 for xiaozy
After=default.target

[Service]
Type=forking
PIDFile=/home/xiaozy/.vnc/5080-MS-eSport-Z890M:22.pid
ExecStart=/opt/TurboVNC/bin/vncserver -geometry 1920x1080 -depth 24 -wm xfce -vgl -localhost :22
ExecStop=/opt/TurboVNC/bin/vncserver -kill :22
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now turbovnc-22.service
```

检查：

```bash
systemctl --user status turbovnc-22.service --no-pager -l
/opt/TurboVNC/bin/vncserver -list
```

停止并禁用：

```bash
systemctl --user disable --now turbovnc-22.service
```

如果服务模式启动失败，先回到手动命令启动，读 `~/.vnc/$(hostname):22.log`。手动方式更容易定位密码、端口、桌面环境和 VirtualGL 问题。

如果服务器 hostname 后续变化，需要同步调整 `PIDFile` 中的 `5080-MS-eSport-Z890M`。TurboVNC 当前脚本生成的 PID 文件格式是 `~/.vnc/<hostname>:<display>.pid`。

## 10. 常见问题处理

连接不上：

- 确认服务器端 `vncserver -list` 有 `:22`。
- 确认 `ss -ltn` 有 `127.0.0.1:5922`。
- 使用 TurboVNC Session Manager 或 SSH 隧道，不要直接连 `xiao-5080:5922`。
- 手动隧道时确认 `ssh -N -L 5922:localhost:5922 xiao-5080` 仍在运行。

黑屏或只有鼠标：

- 查看 `~/.vnc/$(hostname):22.log`。
- 确认启动参数有 `-wm xfce` 或配置文件中有 `$wm = "xfce";`。
- 确认 Xfce 进程存在：`ps -fu "$USER" | grep xfce`。

GPU 没走 NVIDIA：

- 在 VNC 终端中运行 `vglrun -d :0 glxinfo -B`，不要只看普通 `glxinfo -B`。
- 确认 `id` 输出包含 `vglusers`。
- 确认 `/dev/nvidia0`、`/dev/nvidiactl`、`/dev/dri/renderD128` 的组是 `vglusers`。
- 如果刚加组，必须退出所有旧 SSH/桌面会话并重新登录。

端口或 display 冲突：

- `:21` 当前被 `maxw` 使用。
- 推荐 `xiaozy` 使用 `:22`。
- 如果 `:22` 后续被占用，改用 `:23`，同时把所有 `5922` 改成 `5923`。

密码问题：

- 重新设置：`/opt/TurboVNC/bin/vncpasswd`
- 不要删除或修改 `maxw` 的密码文件。
- 不要把 `~/.vnc/passwd` 内容发给别人。

## 11. 如果要严格对齐 maxw 配置

当前能看到的信息已经足够配置 `xiaozy` 的 TurboVNC GPU 桌面。如果需要严格复制 `maxw` 的用户级配置风格，例如是否有自定义 `~/.vnc/turbovncserver.conf`、自定义 `xstartup.turbovnc`、特殊环境变量或启动脚本，请让 `maxw` 身份执行 `docss/maxw_turbovnc_reference_commands.md` 中的采集命令，并提供脱敏后的输出。

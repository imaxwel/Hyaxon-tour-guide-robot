# maxw TurboVNC 对照信息采集命令

本文列出需要 `maxw` 身份执行的命令，用于对照当前 `maxw` 的 TurboVNC 配置。`xiaozy` 当前无法读取 `/home/maxw/.vnc`，因此如果要精确参考 `maxw` 的用户级配置，需要由 `maxw` 提供脱敏后的输出。

当前从 `xiaozy` 可见的信息已经显示：

- `maxw` 正在运行 `:21`
- 端口是 `127.0.0.1:5921`
- 分辨率是 `1920x1080`
- 色深是 `24`
- 桌面是 Xfce
- 启动脚本路径是 `/home/maxw/.vnc/xstartup.turbovnc`

如果只按这些信息配置 `xiaozy`，不一定需要进一步读取 `maxw` 私有文件。只有在需要严格对齐 `maxw` 的自定义配置时，才需要下面的输出。

## 1. 敏感信息规则

不要输出这些内容：

- `~/.vnc/passwd`
- `~/.vnc/x509_private.pem`
- `~/.ssh/*`
- 任何私钥、token、密码、cookie
- 完整未过滤的环境变量

可以输出这些内容：

- `~/.vnc` 目录文件列表
- `~/.vnc/turbovncserver.conf`
- `~/.vnc/xstartup`
- `~/.vnc/xstartup.turbovnc`
- TurboVNC 日志尾部
- `vncserver -list`
- 进程命令行
- 与 `DISPLAY`、`TVNC`、`VGL`、`XDG`、`DBUS` 相关的环境变量

## 2. maxw 登录方式

在 Mac 上，如果你有 `maxw` 的 SSH 权限：

```bash
ssh maxw@xiao-5080
```

如果只能先登录 `xiaozy`，且管理员允许切换用户：

```bash
ssh xiao-5080
sudo -iu maxw
```

当前 `xiaozy` 没有免密 sudo，因此第二种方式可能需要管理员密码或不可用。

## 3. 推荐一次性采集脚本

以 `maxw` 身份在服务器执行：

```bash
out=/tmp/maxw-turbovnc-reference.txt

{
  echo "=== identity ==="
  date -Is
  hostname
  id
  echo "HOME=$HOME"
  echo

  echo "=== turbovnc list ==="
  /opt/TurboVNC/bin/vncserver -list 2>&1 || true
  echo

  echo "=== ~/.vnc metadata ==="
  ls -la ~/.vnc 2>&1 || true
  echo

  echo "=== ~/.vnc files except secrets ==="
  find ~/.vnc -maxdepth 1 -type f \
    ! -name passwd \
    ! -name x509_private.pem \
    -printf '%M %u %g %s %TY-%Tm-%Td %TH:%TM %p\n' 2>/dev/null | sort || true
  echo

  echo "=== turbovnc user config candidates ==="
  for f in \
    ~/.vnc/turbovncserver.conf \
    ~/.vnc/config \
    ~/.vnc/xstartup \
    ~/.vnc/xstartup.turbovnc \
    ~/.vnc/default.turbovnc
  do
    if [ -f "$f" ]; then
      echo "--- $f"
      sed -n '1,240p' "$f"
      echo
    fi
  done

  echo "=== latest vnc logs tail ==="
  for f in ~/.vnc/*.log; do
    [ -f "$f" ] || continue
    echo "--- $f"
    tail -n 180 "$f"
    echo
  done

  echo "=== maxw vnc and desktop processes ==="
  ps -fu "$USER" | grep -E 'Xvnc|vncserver|xfce|gnome-session|mate-session|startplasma|vgl' | grep -v grep || true
  echo

  echo "=== maxw Xvnc command line ==="
  pid="$(pgrep -u "$USER" -f '/opt/TurboVNC/bin/Xvnc :21' | head -n 1 || true)"
  echo "pid=$pid"
  if [ -n "$pid" ]; then
    tr '\0' '\n' < "/proc/$pid/cmdline" 2>/dev/null | nl -ba || true
  fi
  echo

  echo "=== selected maxw Xvnc environment ==="
  if [ -n "$pid" ]; then
    tr '\0' '\n' < "/proc/$pid/environ" 2>/dev/null \
      | grep -E '^(DISPLAY|TVNC_|VGL_|XDG_|DESKTOP_SESSION|GDMSESSION|DBUS_SESSION_BUS_ADDRESS|LD_PRELOAD|PATH)=' \
      | sort || true
  fi
  echo

  echo "=== vnc listeners ==="
  ss -ltnp 2>/dev/null | awk 'NR == 1 || /:59[0-9][0-9]/' || true
  echo

  echo "=== GPU check from maxw :21 session ==="
  if /opt/TurboVNC/bin/vncserver -list 2>/dev/null | grep -q '^:21'; then
    DISPLAY=:21 vglrun -d :0 glxinfo -B 2>&1 \
      | egrep 'direct rendering|OpenGL vendor|OpenGL renderer|OpenGL version' || true
  else
    echo "No maxw :21 session found by vncserver -list."
  fi
} > "$out"

chmod 600 "$out"
echo "$out"
```

然后把输出文件内容发给我：

```bash
sed -n '1,260p' /tmp/maxw-turbovnc-reference.txt
```

如果文件超过 260 行，继续分段：

```bash
sed -n '261,520p' /tmp/maxw-turbovnc-reference.txt
sed -n '521,780p' /tmp/maxw-turbovnc-reference.txt
```

## 4. 最小采集命令

如果不想运行完整脚本，至少提供这些输出：

```bash
id
/opt/TurboVNC/bin/vncserver -list
ls -la ~/.vnc
```

```bash
for f in ~/.vnc/turbovncserver.conf ~/.vnc/xstartup ~/.vnc/xstartup.turbovnc ~/.vnc/default.turbovnc; do
  [ -f "$f" ] || continue
  echo "--- $f"
  sed -n '1,220p' "$f"
done
```

```bash
tail -n 160 ~/.vnc/$(hostname):21.log
```

```bash
ps -fu "$USER" | grep -E 'Xvnc|vncserver|xfce|vgl' | grep -v grep
```

```bash
DISPLAY=:21 vglrun -d :0 glxinfo -B | egrep 'direct rendering|OpenGL vendor|OpenGL renderer|OpenGL version'
```

## 5. 需要关注的差异点

拿到 `maxw` 输出后，重点比较这些项：

- 是否存在 `~/.vnc/turbovncserver.conf`
- 是否显式配置了 `$geometry`、`$depth`、`$wm`、`$useVGL`、`$serverArgs`
- 是否使用了自定义 `xstartup` 或 `xstartup.turbovnc`
- 日志中实际使用的是不是 `xfce.desktop`
- 日志中是否出现 `vglrun +wm`
- GPU 验证里 renderer 是否是 `NVIDIA GeForce RTX 5080`
- 是否有额外环境变量影响 CUDA、OpenGL、VirtualGL 或桌面启动


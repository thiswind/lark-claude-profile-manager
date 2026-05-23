# Lark Claude Profile Manager

`lcp` 是一个本地 CLI，用来管理多个长期运行的 Claude Code + 飞书/Lark bridge 工作环境。

核心模型：

```text
一个任务域 = 一个 profile = 一个飞书机器人 = 一个长期 Docker 容器
```

每个 profile 独立拥有：

- 一个 Docker 容器：`lcp-<profile>`
- 一份 `lark-channel-bridge` 状态
- 一份 `lark-cli` 状态
- 一份日志目录
- 一个可长期演化、可 snapshot 的容器环境

Claude Code 配置从宿主机挂载到容器内复用；项目工作区只挂载宿主机 Desktop，不挂载整盘。

## 当前状态

已验证环境：

- WSL Ubuntu + Docker Desktop
- Windows 原生 Python + Docker Desktop

注意：WSL 和 Windows 原生运行时是两套独立环境：

```text
WSL:     /home/<user>/.lcp
Windows: C:\Users\<user>\.lcp
```

所以在 WSL 里 `lcp profile list` 和在 PowerShell 里 `lcp profile list` 看到的 profile 可能不同。这是预期行为。

## 安装

在项目目录中安装到当前用户 Python 环境：

```bash
python -m pip install --user .
```

开发时建议使用 editable 安装：

```bash
python -m pip install --user -e '.[dev]'
```

Windows PowerShell 中同样使用：

```powershell
python -m pip install --user -e .[dev]
```

如果安装后找不到 `lcp`，检查 Python user scripts 目录是否在 `PATH`。

WSL / Linux 常见路径：

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Windows 常见路径：

```text
%APPDATA%\Python\Python<MAJOR><MINOR>\Scripts
```

例如 Python 3.14：

```text
C:\Users\Administrator\AppData\Roaming\Python\Python314\Scripts
```

更新代码后，如果之前不是 editable 安装，需要重新安装：

```bash
python -m pip install --user --upgrade .
```

## 命令结构

顶层命令只保留 LCP 自身和主功能分组：

```text
lcp init       初始化本机配置
lcp doctor     检查本机环境
lcp profile    管理 profile 生命周期
lcp bridge     管理或代理容器内 lark-channel-bridge
```

旧的顶层命令（如 `lcp create`、`lcp list`、`lcp status`）仍保留为隐藏兼容入口，但新用法应使用 `lcp profile ...`。

## 初始化

首次使用先运行：

```bash
lcp init
```

它会检查：

- 当前运行环境：WSL / Windows / Linux / macOS
- CPU 架构
- 当前宿主用户与 UID/GID
- Desktop 路径
- Docker 可用性与版本
- GPU 检测结果
- Claude Code 配置路径
- Ubuntu LTS / Node.js 策略

并写入：

```text
~/.lcp/config.json
```

之后可随时检查当前环境：

```bash
lcp doctor
```

## 创建 profile

创建一个 profile：

```bash
lcp profile create solid
```

它会：

1. 读取或生成本机配置。
2. 生成 profile 配置。
3. 构建 profile base image：`lcp/solid:base`。
4. 创建长期容器：`lcp-solid`。
5. 启动容器。
6. 安装 Claude Code、`lark-cli`、`lark-channel-bridge`。

跳过运行时工具安装：

```bash
lcp profile create solid --no-install
```

如果同名 profile 或容器已经存在，命令会安全失败并提示处理方式，不会覆盖已有 profile state，也不会抛 Docker traceback。要重建请先删除：

```bash
lcp profile rm solid
```

## 查看和进入 profile

列出 profile：

```bash
lcp profile list
```

查看单个 profile 状态：

```bash
lcp profile status solid
```

进入容器 shell：

```bash
lcp profile shell solid
```

验证容器环境：

```bash
lcp profile verify solid
```

如果不想运行 Claude 非交互检查：

```bash
lcp profile verify solid --no-run-claude
```

## 绑定飞书机器人

`lcp` 不自动创建或绑定飞书机器人。首次配置 bridge 时，用前台模式运行：

```bash
lcp bridge solid run
```

这会在当前终端中运行容器内的：

```bash
lark-channel-bridge run
```

适合扫码、填写配置、调试输出。完成配置并确认能收发消息后，按 `Ctrl+C` 退出前台运行。

## 后台运行 bridge

日常后台运行使用：

```bash
lcp bridge solid start
```

`lcp bridge <profile> start` 的语义是：

1. 启动 profile 容器。
2. 在容器内用 LCP supervisor loop 后台托管：
   ```bash
   lark-channel-bridge run
   ```
3. 检查真实的 `node ... lark-channel-bridge run` 进程是否存在。

它不是代理上游的 `lark-channel-bridge start`。上游 `start` 是 OS daemon/service 语义；LCP 使用容器内后台 supervisor 管理 `run`。

查看状态：

```bash
lcp bridge solid status
```

查看日志：

```bash
lcp bridge solid logs
```

停止后台 bridge：

```bash
lcp bridge solid stop
```

重启后台 bridge 和容器：

```bash
lcp bridge solid restart
```

如果还没有完成首次 QR/配置，`lcp bridge solid start` 会失败并提示先运行：

```bash
lcp bridge solid run
```

## 代理 lark-channel-bridge 命令

除 LCP 托管动作外，`lcp bridge <profile> ...` 会把其它参数原样转发给容器内 `lark-channel-bridge`。

示例：

```bash
lcp bridge solid run
lcp bridge solid ps
lcp bridge solid secrets list
lcp bridge solid --help
```

常用动作可通过 help 查看：

```bash
lcp bridge --help
```

## 删除 profile

profile 和容器是一个生命周期单元。删除时一起删除：

```bash
lcp profile rm solid
```

跳过确认：

```bash
lcp profile rm solid --yes
```

该命令会：

1. 停止 LCP 托管的 bridge。
2. 删除 Docker 容器 `lcp-solid`。
3. 删除 profile state：`~/.lcp/profiles/solid`。

隐藏调试命令 `lcp rm container <name>` 和 `lcp rm profile <name>` 仍保留用于救援，但日常不建议使用。

## Snapshot / Restore

备份 profile 容器镜像：

```bash
lcp profile snapshot solid
```

指定输出目录：

```bash
lcp profile snapshot solid --output /path/to/backup-dir
```

加载 snapshot tar：

```bash
lcp profile restore solid --image-tar /path/to/solid-snapshot.tar
```

当前 restore 只完成 Docker image load。完整的“从 snapshot 重建 profile/container”仍是后续增强项。

## 自动补全

Typer 提供 shell completion 安装命令。根据 `lcp --install-completion` 的提示选择当前 shell：

```bash
lcp --install-completion bash
```

PowerShell：

```powershell
lcp --install-completion powershell
```

安装后通常需要重开终端。

## 测试

运行单元测试：

```bash
python -m pytest tests
```

常用聚焦测试：

```bash
python -m pytest tests/test_cli.py tests/test_bridge.py
```

## 常见问题

### 为什么 WSL 和 Windows 看到的 profile 不一样？

因为它们使用不同的 `~/.lcp`：WSL 是 Linux home，Windows 是 Windows user home。两边可以分别管理不同 profile。

### 为什么只挂载 Desktop？

为了限制容器对宿主机的影响范围。Desktop 是主要人机协作工作区；不挂载整盘可以降低误改系统目录、用户配置、AppData 等敏感路径的风险。

### 为什么容器不用 root？

容器运行用户和宿主用户 UID/GID 对齐，可以减少权限问题，也避免在 Desktop 里生成 root-owned 文件。

### 为什么 Node.js 放进 Dockerfile？

`lark-channel-bridge` 依赖较新的 Node API。LCP 固化 Node.js 24 LTS 到 profile image 层，保证新 profile 有一致的运行基础。

### 为什么 Claude Code 和 bridge 不放进 Dockerfile？

它们更新频率高。放在容器创建后安装，可以让新 profile 创建时拿到当时较新的版本。

### `lcp bridge start` 成功但收不到消息怎么办？

先看状态和日志：

```bash
lcp bridge solid status
lcp bridge solid logs
```

如果提示缺少配置，先运行前台向导：

```bash
lcp bridge solid run
```

如果日志显示 bridge 已连接但仍收不到消息，再检查飞书机器人配置、事件订阅、权限和 `lark-cli` 登录状态。

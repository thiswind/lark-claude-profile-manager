# Lark Claude Profile Manager

`lcp` 是一个本地命令行工具，用来管理多个 Claude Code + 飞书/Lark bridge 工作环境。

你可以为不同任务创建不同 profile。每个 profile 会有自己的容器、飞书 bridge 配置、`lark-cli` 状态和日志。

## 环境要求

- Python 3.11+
- Docker / Docker Desktop
- 可用的 Claude Code 配置

已验证：

- WSL Ubuntu + Docker Desktop
- Windows + Docker Desktop

## 安装

在项目目录中运行：

```bash
python -m pip install --user .
```

开发或频繁更新源码时使用 editable 安装：

```bash
python -m pip install --user -e '.[dev]'
```

Windows PowerShell：

```powershell
python -m pip install --user -e .[dev]
```

如果安装后找不到 `lcp`，把 Python user scripts 目录加入 `PATH`。

WSL / Linux 常见路径：

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Windows 常见路径：

```text
%APPDATA%\Python\Python<MAJOR><MINOR>\Scripts
```

例如：

```text
C:\Users\Administrator\AppData\Roaming\Python\Python314\Scripts
```

更新非 editable 安装：

```bash
python -m pip install --user --upgrade .
```

## 面向宿主机 Claude Code 的运营手册

如果你是一个运行在宿主机上的 Claude Code agent，负责创建、维护、排障和发布 LCP profiles，请先阅读：

[Agent Operations Runbook](docs/agent-operations-runbook.md)

这份手册面向智能体，不是普通用户教程。它定义了 profile/container/bridge/lark-cli/GitHub 的日常操作顺序、安全边界和失败处理规则。

## 快速开始

初始化：

```bash
lcp init
```

检查环境：

```bash
lcp doctor
```

创建 profile：

```bash
lcp profile create solid
```

首次绑定飞书机器人，前台运行 bridge：

```bash
lcp bridge solid run
```

完成二维码/配置流程，确认可用后按 `Ctrl+C` 退出。

后台启动 bridge：

```bash
lcp bridge solid start
```

查看状态：

```bash
lcp bridge solid status
```

查看日志：

```bash
lcp bridge solid logs
```

## 常用命令

### 本机配置

```bash
lcp init
lcp doctor
```

### Profile 管理

```bash
lcp profile create <name>
lcp profile list
lcp profile status <name>
lcp profile shell <name>
lcp profile verify <name>
lcp profile rm <name>
```

跳过创建时的工具安装：

```bash
lcp profile create <name> --no-install
```

跳过 Claude 非交互检查：

```bash
lcp profile verify <name> --no-run-claude
```

删除 profile 时跳过确认：

```bash
lcp profile rm <name> --yes
```

### Bridge 管理

```bash
lcp bridge <name> run
lcp bridge <name> start
lcp bridge <name> status
lcp bridge <name> logs
lcp bridge <name> stop
lcp bridge <name> restart
lcp bridge <name> bind-lark-cli
```

说明：

- `run`：前台运行，用于首次配置、二维码流程和调试。
- `start`：后台运行，日常使用；启动前会自动绑定 profile-local `lark-cli`，失败则退出。
- `logs`：查看 bridge 日志。
- `stop`：停止后台 bridge。
- `restart`：重启后台 bridge 和容器；启动 bridge 前会重新绑定 profile-local `lark-cli`。
- `bind-lark-cli`：手动把 profile-local `lark-cli` 绑定到当前 profile 的机器人。

其它 bridge 参数会转发给容器内的 `lark-channel-bridge`：

```bash
lcp bridge <name> --help
lcp bridge <name> ps
lcp bridge <name> secrets list
```

## Profile 工作目录

容器内 Desktop 路径：

```text
/home/<user>/Desktop
```

默认工作目录：

```text
/home/<user>/Desktop/Projects/lcp_profiles/<profile>
```

例如当前 WSL 环境中：

```text
/home/thiswind/Desktop/Projects/lcp_profiles/solid
```

对应宿主机：

```text
/mnt/c/Users/Administrator/Desktop/Projects/lcp_profiles/solid
```

## 备份和恢复

导出容器 snapshot：

```bash
lcp profile snapshot <name>
```

指定输出目录：

```bash
lcp profile snapshot <name> --output /path/to/backup-dir
```

加载 snapshot tar：

```bash
lcp profile restore <name> --image-tar /path/to/snapshot.tar
```

当前 restore 只加载 Docker image tar，完整重建 profile/container 仍在完善中。

## 自动补全

Bash：

```bash
lcp --install-completion bash
```

PowerShell：

```powershell
lcp --install-completion powershell
```

安装后重开终端。

## WSL 和 Windows 说明

WSL 和 Windows 原生 Python 会使用不同的 LCP 数据目录：

```text
WSL:     /home/<user>/.lcp
Windows: C:\Users\<user>\.lcp
```

所以在 WSL 和 PowerShell 中看到的 profile 列表可能不同。

## 故障排查

### `lcp` 命令找不到

检查 Python user scripts 目录是否在 `PATH`。

### `lcp bridge <name> start` 提示缺少配置

先运行前台配置：

```bash
lcp bridge <name> run
```

完成二维码/配置流程后，再运行：

```bash
lcp bridge <name> start
```

### 后台 bridge 收不到消息

查看状态和日志：

```bash
lcp bridge <name> status
lcp bridge <name> logs
```

如果 bridge 已连接但仍收不到消息，检查飞书机器人事件订阅、权限和 `lark-cli` 登录状态。

### profile 已存在

查看状态：

```bash
lcp profile status <name>
```

如果要重建，先删除：

```bash
lcp profile rm <name>
```

再重新创建。

import json
import shlex

from .host_user import HostUser
from .lark_cli_wrapper import LARK_CLI_WRAPPER_INSTALL
from .models import UBUNTU_LTS_IMAGE
from .runtime import RuntimeManifest
from .version_lock import dependency_npm_install_spec, find_dependency

NODE_MAJOR = 24
BASE_PACKAGES = " ".join(sorted([
    "bash",
    "bash-completion",
    "ca-certificates",
    "coreutils",
    "curl",
    "dnsutils",
    "file",
    "git",
    "gnupg",
    "htop",
    "iproute2",
    "iputils-ping",
    "jq",
    "less",
    "lsof",
    "net-tools",
    "netcat-openbsd",
    "openssh-client",
    "python3",
    "python3-pip",
    "python3-venv",
    "ripgrep",
    "strace",
    "sudo",
    "traceroute",
    "tree",
    "unzip",
    "vim-tiny",
    "wget",
    "zip",
]))


def render_base_dockerfile() -> str:
    return f"""FROM {UBUNTU_LTS_IMAGE}

ARG DEBIAN_FRONTEND=noninteractive

RUN sed -i 's/ noble-backports//g; s/noble-backports//g' /etc/apt/sources.list /etc/apt/sources.list.d/*.list /etc/apt/sources.list.d/*.sources 2>/dev/null || true \
    && apt-get -o Acquire::Retries=3 update \
    && apt-get -o Acquire::Retries=3 install -y {BASE_PACKAGES} \
    && curl -fsSL https://deb.nodesource.com/setup_{NODE_MAJOR}.x | bash - \
    && apt-get -o Acquire::Retries=3 install -y nodejs \
    && npm config set cache /cache/npm --global \
    && rm -rf /var/lib/apt/lists/*

CMD ["sleep", "infinity"]
"""


def render_runtime_dockerfile(manifest: RuntimeManifest) -> str:
    installs = []
    preinstall_steps = []
    for name, tool in manifest.tools.items():
        dependency = find_dependency(tool.versionLockDependency) if tool.versionLockDependency else None
        if dependency and dependency.controlled:
            if not dependency.package:
                raise ValueError(f"{dependency.name}: controlled dependency has no npm package")
            source_dir = f"/cache/tmp/{name}-src"
            package_file = f"/cache/tmp/{name}.tgz"
            repo = str(dependency.controlled.repo).rstrip("/")
            package_name = json.dumps(dependency.package)
            pack_output = f"/cache/tmp/{name}.pack.out"
            pack_parser = "".join([
                "const fs=require('fs');",
                "const text=fs.readFileSync(process.argv[1],'utf8');",
                "const start=text.lastIndexOf('\\n[')>=0?text.lastIndexOf('\\n[')+1:text.indexOf('[');",
                "if(start<0){throw new Error('missing npm pack JSON array');}",
                "const p=JSON.parse(text.slice(start).trim())[0];",
                f"if(!p||p.name!=={package_name}){{process.exit(1);}}",
                "process.stdout.write(p.filename);",
            ])
            preinstall_steps.append(" && ".join([
                f"rm -rf {shlex.quote(source_dir)} {shlex.quote(package_file)} {shlex.quote(pack_output)}",
                f"git clone {shlex.quote(repo + '.git')} {shlex.quote(source_dir)}",
                f"cd {shlex.quote(source_dir)}",
                f"git checkout {shlex.quote(dependency.controlled.commit)}",
                "npm install --include=dev --cache /cache/npm",
                "npm run build",
                f"npm pack --pack-destination /cache/tmp --cache /cache/npm --json > {shlex.quote(pack_output)}",
                f"node -e {shlex.quote(pack_parser)} {shlex.quote(pack_output)} > /cache/tmp/{name}.pack",
                f"mv /cache/tmp/$(cat /cache/tmp/{name}.pack) {shlex.quote(package_file)}",
            ]))
            installs.append(package_file)
            continue
        package = dependency_npm_install_spec(tool.versionLockDependency) if tool.versionLockDependency else tool.package if tool.version == "latest" else f"{tool.package}@{tool.version}"
        installs.append(shlex.quote(package))
    preinstall_command = " && ".join(preinstall_steps) if preinstall_steps else "true"
    install_command = "npm install -g " + " ".join(installs) + " --include=optional --cache /cache/npm" if installs else "true"
    return f"""FROM {manifest.baseImage}

ARG DEBIAN_FRONTEND=noninteractive

RUN mkdir -p /cache/npm /cache/pnpm /cache/pip /cache/tmp /logs \
    && {preinstall_command} \
    && {install_command}

RUN if command -v claude >/dev/null 2>&1; then \
        cd $(npm root -g)/@anthropic-ai/claude-code \
        && pkg=$(case $(node -p 'process.arch') in x64) echo @anthropic-ai/claude-code-linux-x64 ;; arm64) echo @anthropic-ai/claude-code-linux-arm64 ;; esac) \
        && if [ -n "$pkg" ]; then npm install "$pkg" --cache /cache/npm; fi \
        && node install.cjs; \
    fi

RUN {json.dumps(["bash", "-lc", LARK_CLI_WRAPPER_INSTALL])}

CMD ["sleep", "infinity"]
"""


def render_profile_dockerfile(user: HostUser, runtime_image: str | None = None) -> str:
    base_image = runtime_image or "lcp/runtime:latest"
    return f"""FROM {base_image}

ARG DEBIAN_FRONTEND=noninteractive

RUN if getent passwd {user.uid} >/dev/null; then \
        old_user=$(getent passwd {user.uid} | cut -d: -f1); \
        if [ "$old_user" != "{user.name}" ]; then userdel -r "$old_user" 2>/dev/null || userdel "$old_user"; fi; \
    fi \
    && if ! getent group {user.gid} >/dev/null; then groupadd --gid {user.gid} {user.name}; fi \
    && if ! id -u {user.name} >/dev/null 2>&1; then useradd --uid {user.uid} --gid {user.gid} --create-home --shell /bin/bash {user.name}; fi \
    && mkdir -p /home/{user.name}/Desktop/Projects/lcp_profiles /home/{user.name}/.local/share /home/{user.name}/.config /cache/npm /cache/pnpm /cache/pip /cache/tmp /logs \
    && printf '%s ALL=(ALL) NOPASSWD:ALL\\n' {user.name} > /etc/sudoers.d/lcp-{user.name} \
    && chmod 0440 /etc/sudoers.d/lcp-{user.name} \
    && chown -R {user.uid}:{user.gid} /home/{user.name} /cache /logs

ENV HOME=/home/{user.name}
ENV USER={user.name}
ENV NPM_CONFIG_PREFIX=/home/{user.name}/.npm-global
ENV PATH=/home/{user.name}/.npm-global/bin:$PATH

USER {user.uid}:{user.gid}
WORKDIR /home/{user.name}

RUN mkdir -p /home/{user.name}/.npm-global /home/{user.name}/Desktop/Projects/lcp_profiles

CMD ["sleep", "infinity"]
"""

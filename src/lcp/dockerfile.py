from .host_user import HostUser
from .models import UBUNTU_LTS_IMAGE

NODE_MAJOR = 24
BASE_PACKAGES = "ca-certificates curl git gh bash coreutils python3 python3-pip gnupg sudo"


def render_profile_dockerfile(user: HostUser) -> str:
    return f"""FROM {UBUNTU_LTS_IMAGE}

ARG DEBIAN_FRONTEND=noninteractive

RUN sed -i 's/ noble-backports//g; s/noble-backports//g' /etc/apt/sources.list /etc/apt/sources.list.d/*.list /etc/apt/sources.list.d/*.sources 2>/dev/null || true \
    && apt-get -o Acquire::Retries=3 update \
    && apt-get -o Acquire::Retries=3 install -y {BASE_PACKAGES} \
    && curl -fsSL https://deb.nodesource.com/setup_{NODE_MAJOR}.x | bash - \
    && apt-get -o Acquire::Retries=3 install -y nodejs \
    && npm config set cache /cache/npm --global \
    && rm -rf /var/lib/apt/lists/*

RUN if getent passwd {user.uid} >/dev/null; then \
        old_user=$(getent passwd {user.uid} | cut -d: -f1); \
        if [ "$old_user" != "{user.name}" ]; then userdel -r "$old_user" 2>/dev/null || userdel "$old_user"; fi; \
    fi \
    && if ! getent group {user.gid} >/dev/null; then groupadd --gid {user.gid} {user.name}; fi \
    && if ! id -u {user.name} >/dev/null 2>&1; then useradd --uid {user.uid} --gid {user.gid} --create-home --shell /bin/bash {user.name}; fi \
    && mkdir -p /home/{user.name}/Desktop/Projects/Active /cache/npm /cache/pnpm /cache/pip /cache/tmp /logs \
    && chown -R {user.uid}:{user.gid} /home/{user.name} /cache /logs

ENV HOME=/home/{user.name}
ENV USER={user.name}
ENV NPM_CONFIG_PREFIX=/home/{user.name}/.npm-global
ENV PATH=/home/{user.name}/.npm-global/bin:$PATH

USER {user.uid}:{user.gid}
WORKDIR /home/{user.name}

RUN mkdir -p /home/{user.name}/.npm-global /home/{user.name}/Desktop/Projects/Active

CMD ["sleep", "infinity"]
"""

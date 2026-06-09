import json
import shlex

from .version_lock import VersionLockEntry, find_dependency


def controlled_dependency_pack_command(dependency: VersionLockEntry, package_file: str, name: str, npm_cache: str = "/cache/npm") -> str | None:
    if not dependency.controlled:
        return None
    if not dependency.package:
        raise ValueError(f"{dependency.name}: controlled dependency has no npm package")
    source_dir = f"/cache/tmp/{name}-src"
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
    return " && ".join([
        f"rm -rf {shlex.quote(source_dir)} {shlex.quote(package_file)} {shlex.quote(pack_output)}",
        f"git clone {shlex.quote(repo + '.git')} {shlex.quote(source_dir)}",
        f"cd {shlex.quote(source_dir)}",
        f"git checkout {shlex.quote(dependency.controlled.commit)}",
        f"npm install --include=dev --cache {shlex.quote(npm_cache)}",
        "npm run build",
        f"npm pack --pack-destination /cache/tmp --cache {shlex.quote(npm_cache)} --json > {shlex.quote(pack_output)}",
        f"node -e {shlex.quote(pack_parser)} {shlex.quote(pack_output)} > /cache/tmp/{name}.pack",
        f"mv /cache/tmp/$(cat /cache/tmp/{name}.pack) {shlex.quote(package_file)}",
    ])


def controlled_dependency_pack_install_command(identifier: str, package_file: str, name: str | None = None, npm_cache: str = "/cache/npm") -> str | None:
    dependency = find_dependency(identifier)
    package_name = name or dependency.package or identifier
    pack_command = controlled_dependency_pack_command(dependency, package_file, package_name, npm_cache)
    if pack_command is None:
        return None
    return f"{pack_command} && npm install -g {shlex.quote(package_file)} --cache {shlex.quote(npm_cache)}"

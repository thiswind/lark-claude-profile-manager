from pathlib import Path

from pydantic import BaseModel, Field, HttpUrl, model_validator

from . import __version__

VERSION_LOCK_FILE = Path(__file__).with_name("version_lock.json")
CRITICAL_POLICIES = {"controlled-fork", "controlled-mirror"}


class ControlledDependency(BaseModel):
    repo: HttpUrl
    tag: str
    commit: str


class UpstreamDependency(BaseModel):
    repo: HttpUrl
    branch: str | None = None
    tag: str | None = None
    commit: str


class ValidationRecord(BaseModel):
    lcpVersion: str
    validatedAt: str
    profiles: list[str] = Field(default_factory=list)
    commands: list[str] = Field(default_factory=list)


class VersionLockEntry(BaseModel):
    name: str
    role: str
    risk: str
    policy: str
    package: str | None = None
    version: str | None = None
    controlled: ControlledDependency | None = None
    upstream: UpstreamDependency | None = None
    patches: list[str] = Field(default_factory=list)
    validation: ValidationRecord | None = None

    @model_validator(mode="after")
    def validate_policy_requirements(self):
        if self.policy in CRITICAL_POLICIES:
            if self.controlled is None:
                raise ValueError(f"{self.name}: controlled dependency requires repo, tag, and commit")
            if self.upstream is None:
                raise ValueError(f"{self.name}: controlled dependency requires upstream provenance")
            if self.controlled.tag in {"latest", "main", "master"}:
                raise ValueError(f"{self.name}: controlled tag must not be floating")
        if self.version == "latest" and self.risk == "critical":
            raise ValueError(f"{self.name}: critical dependency must not use latest")
        return self


class VersionLock(BaseModel):
    schemaVersion: int = 1
    lcpVersion: str
    generatedAt: str
    dependencies: list[VersionLockEntry]

    @model_validator(mode="after")
    def validate_release_version(self):
        for dependency in self.dependencies:
            if dependency.validation and dependency.validation.lcpVersion != self.lcpVersion:
                raise ValueError(f"{dependency.name}: validation version does not match lock version")
        return self


def load_version_lock(path: Path = VERSION_LOCK_FILE) -> VersionLock:
    return VersionLock.model_validate_json(path.read_text(encoding="utf-8"))


def dependency_npm_install_spec(identifier: str, lock: VersionLock | None = None) -> str:
    lock = lock or load_version_lock()
    for dependency in lock.dependencies:
        if identifier not in {dependency.name, dependency.package}:
            continue
        if dependency.controlled:
            repo = str(dependency.controlled.repo).rstrip("/")
            return f"git+{repo}.git#{dependency.controlled.commit}"
        if not dependency.package:
            raise ValueError(f"{identifier}: dependency has no npm package")
        if dependency.version and dependency.version != "latest":
            return f"{dependency.package}@{dependency.version}"
        return dependency.package
    raise ValueError(f"{identifier}: dependency not found in version lock")


def verify_version_lock(lock: VersionLock | None = None) -> list[str]:
    lock = lock or load_version_lock()
    failures: list[str] = []
    if lock.lcpVersion != __version__:
        failures.append(f"lock version {lock.lcpVersion} does not match package version {__version__}")
    for dependency in lock.dependencies:
        if dependency.policy in CRITICAL_POLICIES:
            if dependency.controlled is None:
                failures.append(f"{dependency.name}: missing controlled repo/tag/commit")
                continue
            if dependency.controlled.tag in {"latest", "main", "master"}:
                failures.append(f"{dependency.name}: controlled tag is floating: {dependency.controlled.tag}")
            if not dependency.controlled.commit:
                failures.append(f"{dependency.name}: missing controlled commit")
            if dependency.upstream is None:
                failures.append(f"{dependency.name}: missing upstream provenance")
        if dependency.risk == "critical" and dependency.version == "latest":
            failures.append(f"{dependency.name}: critical dependency uses latest")
    return failures

from typing import Literal

from pydantic import BaseModel, Field


IntegrationStatus = Literal[
    "disabled",
    "active",
    "pending_recreate",
    "pending_install",
    "pending_config",
    "pending_verify",
    "error",
]


class IntegrationCapabilities(BaseModel):
    requiresHostTool: bool = True
    requiresHostAuth: bool = True
    supportsSnapshot: bool = True
    requiresMount: bool = False
    requiresContainerInstall: bool = False
    supportsExactVersionInstall: bool = False
    supportsReuseMatching: bool = False
    canVerifyContainer: bool = True


class IntegrationDesiredState(BaseModel):
    enabled: bool = False
    grantedAt: str | None = None
    hostVersion: str | None = None
    snapshotPath: str | None = None
    snapshotId: str | None = None
    config: dict[str, str] = Field(default_factory=dict)


class IntegrationEffectiveState(BaseModel):
    status: IntegrationStatus = "disabled"
    appliedAt: str | None = None
    containerVersion: str | None = None
    reason: str | None = None
    lastError: str | None = None


class ProfileIntegrationState(BaseModel):
    desired: IntegrationDesiredState = Field(default_factory=IntegrationDesiredState)
    effective: IntegrationEffectiveState = Field(default_factory=IntegrationEffectiveState)


class ProfileIntegrations(BaseModel):
    providers: dict[str, ProfileIntegrationState] = Field(default_factory=dict)


class HostCheck(BaseModel):
    provider: str
    ok: bool
    version: str | None = None
    authPath: str | None = None
    message: str = ""
    details: dict[str, str] = Field(default_factory=dict)


class IntegrationMount(BaseModel):
    hostPath: str
    containerPath: str
    mode: Literal["ro", "rw"] = "ro"


class ProviderInfo(BaseModel):
    name: str
    description: str
    capabilities: IntegrationCapabilities
    host: HostCheck


class SnapshotFile(BaseModel):
    path: str
    sha256: str
    size: int


class SnapshotMetadata(BaseModel):
    provider: str
    snapshotId: str
    capturedAt: str
    hostVersion: str | None = None
    sourcePath: str
    files: list[SnapshotFile] = Field(default_factory=list)


class IntegrationPlanStep(BaseModel):
    provider: str
    action: str
    reason: str


class IntegrationPlan(BaseModel):
    profile: str
    steps: list[IntegrationPlanStep] = Field(default_factory=list)


class IntegrationVerifyResult(BaseModel):
    provider: str
    command: str
    ok: bool
    output: str = ""

from datetime import UTC, datetime
from pathlib import Path

from lcp.models import Profile
from lcp.store import LcpStore

from .models import (
    HostCheck,
    IntegrationMount,
    IntegrationPlan,
    IntegrationPlanStep,
    IntegrationVerifyResult,
    ProfileIntegrationState,
    ProviderInfo,
)
from .registry import IntegrationRegistry
from .snapshot import capture_snapshot, move_snapshot_to_trash


class IntegrationService:
    def __init__(self, store: LcpStore, registry: IntegrationRegistry | None = None):
        self.store = store
        self.registry = registry or IntegrationRegistry()

    def list_providers(self) -> list[ProviderInfo]:
        return [ProviderInfo(name=provider.name, description=provider.description, capabilities=provider.capabilities(), host=provider.check_host()) for provider in self.registry.list()]

    def doctor(self, provider_name: str) -> HostCheck:
        return self.registry.get(provider_name).check_host()

    def mounts(self, profile: Profile) -> list[IntegrationMount]:
        mounts: list[IntegrationMount] = []
        for name, state in profile.integrations.providers.items():
            if not state.desired.enabled:
                continue
            provider = self.registry.get(name)
            provider.prepare(self.store, profile)
            mounts.extend(provider.mounts(self.store, profile))
        return mounts

    def install_commands(self, profile: Profile, provider_name: str, reuse_matching: bool = False) -> list[str]:
        return self.registry.get(provider_name).install_commands(profile, reuse_matching=reuse_matching)

    def configure_commands(self, profile: Profile, provider_name: str) -> list[str]:
        return self.registry.get(provider_name).configure_commands(profile)

    def revoke_commands(self, profile: Profile, provider_name: str) -> list[str]:
        return self.registry.get(provider_name).revoke_commands(profile)

    def verify_commands(self, profile: Profile, provider_name: str) -> list[str]:
        return self.registry.get(provider_name).verify_commands(profile)

    def plan(self, profile: Profile) -> IntegrationPlan:
        steps: list[IntegrationPlanStep] = []
        for name in sorted(profile.integrations.providers):
            state = profile.integrations.providers[name]
            provider = self.registry.get(name)
            if not state.desired.enabled:
                if state.effective.status != "disabled":
                    if provider.capabilities().requiresMount:
                        steps.append(IntegrationPlanStep(provider=name, action="recreate", reason="integration revoked; recreate container to remove mounts"))
                    else:
                        steps.append(IntegrationPlanStep(provider=name, action="disable", reason="integration revoked; remove LCP-owned container configuration"))
                continue
            capabilities = provider.capabilities()
            if capabilities.requiresContainerInstall:
                steps.append(IntegrationPlanStep(provider=name, action="install", reason="provider requires CLI inside container"))
            if provider.configure_commands(profile):
                steps.append(IntegrationPlanStep(provider=name, action="configure", reason="provider has container configuration commands"))
            if capabilities.requiresMount:
                steps.append(IntegrationPlanStep(provider=name, action="recreate", reason="provider requires read-only auth snapshot mount"))
            if capabilities.canVerifyContainer:
                steps.append(IntegrationPlanStep(provider=name, action="verify", reason="provider supports container verification"))
        return IntegrationPlan(profile=profile.name, steps=steps)

    def grant(self, profile: Profile, provider_name: str, config: dict[str, str] | None = None) -> Profile:
        provider = self.registry.get(provider_name)
        check = provider.check_config(config) if config is not None else provider.check_host()
        if not check.ok:
            raise RuntimeError(check.message or f"{provider_name} is not ready on host")
        now = datetime.now(UTC).isoformat()
        state = profile.integrations.providers.get(provider_name, ProfileIntegrationState())
        state.desired.enabled = True
        state.desired.grantedAt = now
        state.desired.hostVersion = check.version
        state.desired.config = provider.desired_config(check)
        state.effective.status = "pending_recreate" if provider.capabilities().requiresMount else "pending_config"
        state.effective.reason = "granted; run `lcp integration apply`"
        state.effective.lastError = None
        if provider.capabilities().supportsSnapshot and check.authPath:
            integration_dir = self.store.ensure_integration_dir(profile.name, provider_name)
            snapshot_dir = integration_dir / "snapshot"
            metadata = capture_snapshot(provider_name, Path(check.authPath), snapshot_dir, check.version)
            state.desired.snapshotPath = str(snapshot_dir)
            state.desired.snapshotId = metadata.snapshotId
        profile.integrations.providers[provider_name] = state
        provider.prepare(self.store, profile)
        return profile

    def revoke(self, profile: Profile, provider_name: str) -> Profile:
        self.registry.get(provider_name)
        state = profile.integrations.providers.get(provider_name, ProfileIntegrationState())
        state.desired.enabled = False
        state.desired.config = {}
        state.desired.hostVersion = None
        snapshot_id = state.desired.snapshotId
        if state.desired.snapshotPath:
            integration_dir = self.store.ensure_integration_dir(profile.name, provider_name)
            move_snapshot_to_trash(integration_dir / "snapshot", integration_dir / "trash", snapshot_id)
        state.desired.snapshotPath = None
        state.desired.snapshotId = None
        self.registry.get(provider_name).cleanup(self.store, profile)
        if self.registry.get(provider_name).capabilities().requiresMount:
            state.effective.status = "pending_recreate"
            state.effective.reason = "revoked; run `lcp integration apply` to remove mounts"
        else:
            state.effective.status = "pending_config"
            state.effective.reason = "revoked; run `lcp integration apply` to remove container configuration"
        state.effective.lastError = None
        profile.integrations.providers[provider_name] = state
        return profile

    def verify(self, adapter, profile: Profile, provider_name: str | None = None) -> list[IntegrationVerifyResult]:
        provider_names = [provider_name] if provider_name else sorted(profile.integrations.providers)
        results: list[IntegrationVerifyResult] = []
        for name in provider_names:
            state = profile.integrations.providers.get(name)
            if not state or not state.desired.enabled:
                raise RuntimeError(f"{name} is not granted for profile {profile.name}")
            commands = self.verify_commands(profile, name)
            if not commands:
                results.append(IntegrationVerifyResult(provider=name, command="", ok=True, output="no verification command"))
                continue
            for command in commands:
                result = adapter.exec(profile, command)
                results.append(IntegrationVerifyResult(provider=name, command=command, ok=result.exit_code == 0, output=result.output.strip()))
        return results

    def apply(self, adapter, profile: Profile, reuse_matching: bool = False, progress=None) -> tuple[Profile, list[IntegrationVerifyResult]]:
        disabled_names = sorted(name for name, state in profile.integrations.providers.items() if not state.desired.enabled and state.effective.status != "disabled")
        for name in disabled_names:
            state = profile.integrations.providers[name]
            try:
                provider = self.registry.get(name)
                for command in self.revoke_commands(profile, name):
                    if progress:
                        progress(f"revoke {name}: {provider.redact(command)}")
                    result = adapter.exec(profile, command)
                    if result.exit_code != 0:
                        raise RuntimeError(result.output.strip() or f"revoke failed: {name}")
                state.effective.status = "disabled"
                state.effective.reason = "disabled"
                state.effective.lastError = None
            except RuntimeError as exc:
                state.effective.status = "error"
                state.effective.lastError = str(exc)
                state.effective.reason = "revoke cleanup failed"
                raise
        active_names = sorted(name for name, state in profile.integrations.providers.items() if state.desired.enabled)
        for name in active_names:
            state = profile.integrations.providers[name]
            provider = self.registry.get(name)
            try:
                for command in self.install_commands(profile, name, reuse_matching=reuse_matching):
                    if progress:
                        progress(f"install {name}: {provider.redact(command)}")
                    result = adapter.exec(profile, command)
                    if result.exit_code != 0:
                        raise RuntimeError(result.output.strip() or f"install failed: {name}")
                for command in self.configure_commands(profile, name):
                    if progress:
                        progress(f"configure {name}: {provider.redact(command)}")
                    result = adapter.exec(profile, command)
                    if result.exit_code != 0:
                        raise RuntimeError(result.output.strip() or f"configure failed: {name}")
                state.effective.status = "pending_verify"
                state.effective.reason = "installed and configured; verification pending"
                state.effective.lastError = None
            except RuntimeError as exc:
                state.effective.status = "error"
                state.effective.lastError = str(exc)
                state.effective.reason = "apply failed"
                raise
        results = self.verify(adapter, profile) if active_names else []
        failures = [result for result in results if not result.ok]
        now = datetime.now(UTC).isoformat()
        for name in active_names:
            state = profile.integrations.providers[name]
            provider_failures = [result for result in failures if result.provider == name]
            if provider_failures:
                state.effective.status = "error"
                state.effective.reason = "verification failed"
                state.effective.lastError = "\n".join(result.output for result in provider_failures if result.output)
            else:
                state.effective.status = "active"
                state.effective.appliedAt = now
                state.effective.containerVersion = state.desired.hostVersion
                state.effective.reason = "applied"
                state.effective.lastError = None
        for name, state in profile.integrations.providers.items():
            if not state.desired.enabled:
                state.effective.status = "disabled"
                state.effective.reason = "disabled"
                state.effective.lastError = None
        return profile, results

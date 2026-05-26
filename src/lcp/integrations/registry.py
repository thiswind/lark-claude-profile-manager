from .base import IntegrationProvider
from .providers.git import GitProvider
from .providers.github import GitHubProvider
from .providers.proxy import ProxyProvider
from .providers.vercel import VercelProvider


def default_providers() -> dict[str, IntegrationProvider]:
    providers: list[IntegrationProvider] = [GitProvider(), GitHubProvider(), ProxyProvider(), VercelProvider()]
    return {provider.name: provider for provider in providers}


class IntegrationRegistry:
    def __init__(self, providers: dict[str, IntegrationProvider] | None = None):
        self._providers = providers or default_providers()

    def list(self) -> list[IntegrationProvider]:
        return [self._providers[name] for name in sorted(self._providers)]

    def get(self, name: str) -> IntegrationProvider:
        try:
            return self._providers[name]
        except KeyError as exc:
            raise ValueError(f"unknown integration provider: {name}") from exc

from abc import ABC, abstractmethod

from lcp.models import Profile
from lcp.store import LcpStore

from .models import HostCheck, IntegrationCapabilities, IntegrationMount


class IntegrationProvider(ABC):
    name: str
    description: str

    @abstractmethod
    def capabilities(self) -> IntegrationCapabilities:
        raise NotImplementedError

    @abstractmethod
    def check_host(self) -> HostCheck:
        raise NotImplementedError

    def desired_config(self, check: HostCheck) -> dict[str, str]:
        return check.details

    def mounts(self, store: LcpStore, profile: Profile) -> list[IntegrationMount]:
        return []

    def install_commands(self, profile: Profile, reuse_matching: bool = False) -> list[str]:
        return []

    def configure_commands(self, profile: Profile) -> list[str]:
        return []

    def verify_commands(self, profile: Profile) -> list[str]:
        return []

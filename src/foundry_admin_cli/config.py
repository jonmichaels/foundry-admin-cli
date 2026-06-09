"""Versioned Foundry instance configuration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FoundryInstance:
    """Local Foundry instance paths and process metadata."""

    version: str
    install_dir: Path
    data_dir: Path
    url: str
    pm2_name: str

    @property
    def options_path(self) -> Path:
        return self.data_dir / "Config" / "options.json"

    @property
    def worlds_dir(self) -> Path:
        return self.data_dir / "Data" / "worlds"

    @property
    def systems_dir(self) -> Path:
        return self.data_dir / "Data" / "systems"

    @property
    def modules_dir(self) -> Path:
        return self.data_dir / "Data" / "modules"


INSTANCES: dict[str, FoundryInstance] = {
    "v13": FoundryInstance(
        version="v13",
        install_dir=Path("/home/jon/foundry"),
        data_dir=Path("/home/jon/foundryuserdata"),
        url="http://noisy.humung.us:30000/",
        pm2_name="foundry-v13",
    ),
    "v14": FoundryInstance(
        version="v14",
        install_dir=Path("/home/jon/foundry14"),
        data_dir=Path("/home/jon/foundryuserdata14"),
        url="http://noisy.humung.us:30001/",
        pm2_name="foundry-v14",
    ),
}


def get_instance(version: str) -> FoundryInstance:
    """Return configured instance or raise a CLI-friendly ValueError."""

    try:
        return INSTANCES[version]
    except KeyError as exc:
        valid = ", ".join(sorted(INSTANCES))
        raise ValueError(f"Unknown Foundry version '{version}'. Expected one of: {valid}") from exc

"""Shadow identity log. Never skips a capture. kvnloo/cua#11."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ShadowSample:
    surface: str
    identity: str
    invalidators: tuple[str, ...]
    skip_capture: bool = False

    def __post_init__(self) -> None:
        if self.skip_capture:
            raise RuntimeError("shadow probe must not skip captures")


def record(surface: str, identity: str, invalidators: tuple[str, ...] = ()) -> ShadowSample:
    return ShadowSample(surface, identity, invalidators, skip_capture=False)

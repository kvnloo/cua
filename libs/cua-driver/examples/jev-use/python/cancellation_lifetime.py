"""Request-scoped cancellation order. kvnloo/cua#9.

Capacity is released only after the native job that owns it has exited.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Lifetime:
    issuance: str
    events: list[str] = field(default_factory=list)
    native_exited: bool = False
    released: bool = False

    def admit(self) -> None:
        self.events.append(f"admitted:{self.issuance}")

    def observe_cancel(self) -> None:
        self.events.append(f"cancellation-observed:{self.issuance}")

    def native_exit(self) -> None:
        self.native_exited = True
        self.events.append(f"native-exit:{self.issuance}")

    def release(self) -> None:
        if not self.native_exited:
            raise RuntimeError("capacity released before native exit")
        self.released = True
        self.events.append(f"permit-released:{self.issuance}")

    def finish(self, other_issuance: str | None = None) -> None:
        if other_issuance is not None and other_issuance != self.issuance:
            raise RuntimeError("cancel reached the wrong issuance")
        if not self.released:
            raise RuntimeError("public result returned before permit release")
        self.events.append(f"public-result:{self.issuance}")

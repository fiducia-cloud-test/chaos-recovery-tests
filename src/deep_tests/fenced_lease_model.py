from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


class LeaseRejected(RuntimeError):
    """The requested transition is not authorized by the current lease."""


class TokenExhausted(RuntimeError):
    """No fresh fencing token can be represented safely."""


class InvalidSnapshot(ValueError):
    """A durable snapshot would weaken the fencing guarantees."""


@dataclass(frozen=True)
class Lease:
    holder: str
    token: int
    deadline: int


@dataclass(frozen=True)
class LeaseSnapshot:
    now: int
    last_minted_token: int
    lease: Optional[Lease]


@dataclass(frozen=True)
class ResourceSnapshot:
    highest_fence: int
    value: int


class LeaseAuthority:
    """Small independent oracle for lease and monotonic-token semantics."""

    def __init__(self, max_token: int = 4) -> None:
        if max_token < 1:
            raise ValueError("max_token must be positive")
        self.max_token = max_token
        self.now = 0
        self.last_minted_token = 0
        self.lease: Optional[Lease] = None

    def _expire_due(self) -> None:
        if self.lease is not None and self.lease.deadline <= self.now:
            self.lease = None

    def advance(self, ticks: int = 1) -> None:
        if ticks < 0:
            raise ValueError("logical time cannot move backward")
        self.now += ticks
        self._expire_due()

    def acquire(self, holder: str, ttl: int) -> Lease:
        if not holder or ttl <= 0:
            raise LeaseRejected("holder and positive ttl are required")
        self._expire_due()
        if self.lease is not None:
            raise LeaseRejected("a live lease already owns the resource")
        if self.last_minted_token == self.max_token:
            raise TokenExhausted("fresh fencing token space is exhausted")
        self.last_minted_token += 1
        self.lease = Lease(holder, self.last_minted_token, self.now + ttl)
        return self.lease

    def renew(self, holder: str, token: int, ttl: int) -> Lease:
        if ttl <= 0:
            raise LeaseRejected("positive ttl is required")
        self._expire_due()
        if self.lease is None or (self.lease.holder, self.lease.token) != (holder, token):
            raise LeaseRejected("renewal requires the exact live holder and token")
        self.lease = Lease(holder, token, max(self.lease.deadline, self.now + ttl))
        return self.lease

    def release(self, holder: str, token: int) -> None:
        self._expire_due()
        if self.lease is None or (self.lease.holder, self.lease.token) != (holder, token):
            raise LeaseRejected("release requires the exact live holder and token")
        self.lease = None

    def snapshot(self) -> LeaseSnapshot:
        self._expire_due()
        return LeaseSnapshot(self.now, self.last_minted_token, self.lease)

    @classmethod
    def restore(cls, snapshot: LeaseSnapshot, max_token: int = 4) -> "LeaseAuthority":
        if not 0 <= snapshot.last_minted_token <= max_token or snapshot.now < 0:
            raise InvalidSnapshot("token or time is outside the configured domain")
        lease = snapshot.lease
        if lease is not None and (
            not lease.holder
            or lease.token < 1
            or lease.token > snapshot.last_minted_token
            or lease.deadline <= snapshot.now
        ):
            raise InvalidSnapshot("snapshot contains an invalid or expired lease")
        restored = cls(max_token=max_token)
        restored.now = snapshot.now
        restored.last_minted_token = snapshot.last_minted_token
        restored.lease = lease
        return restored

    def assert_invariants(self) -> None:
        assert self.now >= 0
        assert 0 <= self.last_minted_token <= self.max_token
        if self.lease is not None:
            assert self.lease.holder
            assert 1 <= self.lease.token <= self.last_minted_token
            assert self.lease.deadline > self.now


class FencedResource:
    """Downstream contract: install a grant's fence before accepting its writes."""

    def __init__(self) -> None:
        self.highest_fence = 0
        self.value = 0

    def install_fence(self, token: int) -> None:
        if token < self.highest_fence or token < 1:
            raise LeaseRejected("fences must be positive and monotonic")
        self.highest_fence = token

    def write(self, token: int, value: int) -> None:
        if token != self.highest_fence:
            raise LeaseRejected("write does not carry the authoritative fence")
        self.value = value

    def snapshot(self) -> ResourceSnapshot:
        return ResourceSnapshot(self.highest_fence, self.value)

    @classmethod
    def restore(cls, snapshot: ResourceSnapshot) -> "FencedResource":
        if snapshot.highest_fence < 0:
            raise InvalidSnapshot("resource fence cannot be negative")
        restored = cls()
        restored.highest_fence = snapshot.highest_fence
        restored.value = snapshot.value
        return restored


def assert_restore_compatible(authority: LeaseAuthority, resource: FencedResource) -> None:
    """Fail closed instead of reusing a token forgotten by an old snapshot."""

    if authority.last_minted_token < resource.highest_fence:
        raise InvalidSnapshot("authority snapshot predates the downstream fencing epoch")

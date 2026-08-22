import random
import unittest

from deep_tests.fenced_lease_model import (
    FencedResource,
    InvalidSnapshot,
    Lease,
    LeaseAuthority,
    LeaseRejected,
    LeaseSnapshot,
    TokenExhausted,
    assert_restore_compatible,
)


class FencedLeaseRecoveryTests(unittest.TestCase):
    def test_partitioned_old_holder_cannot_write_after_successor_fence(self) -> None:
        authority = LeaseAuthority()
        resource = FencedResource()

        old_lease = authority.acquire("partitioned-a", ttl=2)
        resource.install_fence(old_lease.token)
        resource.write(old_lease.token, 10)
        authority.advance(2)

        successor = authority.acquire("healthy-b", ttl=3)
        resource.install_fence(successor.token)
        resource.write(successor.token, 20)

        with self.assertRaises(LeaseRejected):
            resource.write(old_lease.token, 99)
        with self.assertRaises(LeaseRejected):
            authority.renew(old_lease.holder, old_lease.token, ttl=3)
        with self.assertRaises(LeaseRejected):
            authority.release(old_lease.holder, old_lease.token)
        self.assertEqual(resource.value, 20)

    def test_snapshot_round_trip_preserves_token_and_rejects_rollback(self) -> None:
        authority = LeaseAuthority()
        resource = FencedResource()
        first = authority.acquire("a", ttl=1)
        resource.install_fence(first.token)
        stale_snapshot = authority.snapshot()
        authority.advance(1)
        second = authority.acquire("b", ttl=2)
        resource.install_fence(second.token)

        restored_resource = FencedResource.restore(resource.snapshot())
        rolled_back_authority = LeaseAuthority.restore(stale_snapshot)
        with self.assertRaises(InvalidSnapshot):
            assert_restore_compatible(rolled_back_authority, restored_resource)

        current = LeaseAuthority.restore(authority.snapshot())
        assert_restore_compatible(current, restored_resource)
        self.assertEqual(current.last_minted_token, second.token)

    def test_invalid_snapshot_and_token_exhaustion_fail_closed(self) -> None:
        with self.assertRaises(InvalidSnapshot):
            LeaseAuthority.restore(LeaseSnapshot(5, 1, Lease("a", 1, 5)))

        authority = LeaseAuthority(max_token=2)
        for holder in ("a", "b"):
            lease = authority.acquire(holder, ttl=1)
            authority.advance(1)
            self.assertEqual(lease.token, authority.last_minted_token)
        with self.assertRaises(TokenExhausted):
            authority.acquire("c", ttl=1)

    def test_bounded_transition_exploration_preserves_invariants(self) -> None:
        initial = LeaseAuthority(max_token=3).snapshot()
        frontier = {initial}
        seen = {initial}
        for _depth in range(8):
            following = set()
            for snapshot in frontier:
                for action in self._actions(snapshot):
                    candidate = LeaseAuthority.restore(snapshot, max_token=3)
                    try:
                        action(candidate)
                    except (LeaseRejected, TokenExhausted):
                        continue
                    candidate.assert_invariants()
                    reached = candidate.snapshot()
                    if reached not in seen:
                        seen.add(reached)
                        following.add(reached)
            frontier = following
        self.assertGreaterEqual(len(seen), 50)
        self.assertTrue(any(state.last_minted_token == 3 for state in seen))

    def test_deterministic_partition_and_restore_matrix(self) -> None:
        for seed in range(100):
            randomizer = random.Random(seed)
            authority = LeaseAuthority(max_token=20)
            resource = FencedResource()
            snapshots = []
            for _step in range(80):
                authority.advance(randomizer.randrange(2))
                if authority.lease is None:
                    try:
                        lease = authority.acquire(
                            randomizer.choice(("a", "b", "c")),
                            randomizer.randrange(1, 4),
                        )
                        resource.install_fence(lease.token)
                    except TokenExhausted:
                        pass
                else:
                    lease = authority.lease
                    choice = randomizer.randrange(4)
                    try:
                        if choice == 0:
                            authority.renew(lease.holder, lease.token, randomizer.randrange(1, 4))
                        elif choice == 1:
                            authority.release(lease.holder, lease.token)
                        elif choice == 2:
                            resource.write(lease.token, randomizer.randrange(10_000))
                        else:
                            resource.write(max(1, lease.token - 1), -1)
                    except LeaseRejected:
                        pass
                if randomizer.randrange(7) == 0:
                    snapshots.append((authority.snapshot(), resource.snapshot()))
                authority.assert_invariants()
                self.assertLessEqual(resource.highest_fence, authority.last_minted_token)

            for authority_snapshot, resource_snapshot in snapshots:
                restored_authority = LeaseAuthority.restore(authority_snapshot, max_token=20)
                restored_resource = FencedResource.restore(resource_snapshot)
                assert_restore_compatible(restored_authority, restored_resource)

    @staticmethod
    def _actions(snapshot):
        def advance(authority):
            authority.advance(1)

        yield advance
        for holder in ("a", "b"):
            for ttl in (1, 2):
                yield lambda authority, holder=holder, ttl=ttl: authority.acquire(holder, ttl)
        for holder in ("a", "b"):
            for token in range(1, 4):
                yield lambda authority, holder=holder, token=token: authority.renew(
                    holder, token, 2
                )
                yield lambda authority, holder=holder, token=token: authority.release(
                    holder, token
                )


if __name__ == "__main__":
    unittest.main()

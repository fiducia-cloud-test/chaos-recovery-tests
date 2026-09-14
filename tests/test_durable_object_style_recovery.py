import unittest

from deep_tests.chaos_model import DurableService, Operation, Replica, SimulatedCrash, simulate


class DurableObjectStyleRecoveryTests(unittest.TestCase):
    def test_crash_after_journal_replays_exactly_once_after_recovery(self) -> None:
        service = DurableService()
        operation = Operation("op-1", "account-a", 41, 1)
        with self.assertRaises(SimulatedCrash):
            service.receive(operation, "crash_after_journal")
        self.assertNotIn(operation.key, service.committed)
        self.assertIn(operation.key, service.journal)

        service.recover()
        self.assertEqual(service.materialized["account-a"], 41)
        self.assertEqual(service.side_effect_counts[operation.key], 1)

        service.receive(operation)
        self.assertEqual(service.side_effect_counts[operation.key], 1)

    def test_replica_reordering_never_regresses_entity_sequence(self) -> None:
        replica = Replica()
        newest = Operation("new", "entity-a", 30, 3)
        oldest = Operation("old", "entity-a", 10, 1)
        middle = Operation("middle", "entity-a", 20, 2)

        for operation in (newest, oldest, middle, newest, oldest):
            replica.apply(operation)

        self.assertEqual(replica.entity_sequences["entity-a"], 3)
        self.assertEqual(replica.state["entity-a"], 30)
        self.assertEqual(replica.applied, {"new", "old", "middle"})

    def test_heavy_fault_matrix_produces_retries_but_exactly_once_side_effects(self) -> None:
        saw_retry = False
        for seed in range(64, 96):
            result = simulate(seed, operations=320)
            saw_retry = saw_retry or result.retries > 0
            self.assertEqual(len(result.side_effect_counts), 320, f"seed={seed}")
            self.assertTrue(all(count == 1 for count in result.side_effect_counts.values()), f"seed={seed}")
            for replica_state in result.replica_states:
                self.assertEqual(replica_state, result.primary_state, f"seed={seed}")
        self.assertTrue(saw_retry, "fault matrix should actually exercise retry recovery")


if __name__ == "__main__":
    unittest.main()

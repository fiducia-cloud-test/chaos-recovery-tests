# Deep test strategy

## Scope

Suite: `chaos`
Test organization: `fiducia-cloud-test`
Primary organization: `fiducia-cloud`

## Invariants

- every randomized test uses an explicit deterministic seed;
- retries, duplicates, migrations, and rejected inputs are observable assertions, not sleeps;
- test data is synthetic and contains no production credentials or customer payloads;
- the suite runs without network access by default;
- a product adapter must preserve the reference model and publish the seed and minimized trace on failure;
- scheduled CI is defense in depth; pull-request and main-branch checks remain authoritative.
- every downstream write carries an installed fencing token, and a partitioned former holder cannot overwrite a successor;
- snapshot recovery preserves the last minted token and fails closed when an authority snapshot predates the downstream fence;
- bounded exhaustive exploration and deterministic randomized traces exercise the same safety contract independently of the production implementation.

## Expansion path

1. Add a versioned adapter for the primary repository contract.
2. Add sanitized golden fixtures owned by the canonical interface repository.
3. Run the same trace against the reference model and implementation.
4. Retain failing seeds as regression tests.
5. Link behavior changes to the matching Linear issue and repository PR.

#!/usr/bin/env python3
"""
Test script for the Collision engine's no-repeat vector sampler
(CollisionVectorSampler). See test_preferences.py for the cultural artifacts
intensity scaling fix, which lives in protocol_builder.py and is shared by
all three engines, not just Collision.
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from lectionary_engines.engines.collision_sampler import CollisionVectorSampler, JSONFileStateStore
from lectionary_engines.protocols import collision_protocol


def test_sampler_no_repeats_within_one_pass():
    print("=" * 60)
    print("Test 1: Sampler draws every item exactly once per pass")
    print("=" * 60)

    pools = {"cultural": [f"item-{i}" for i in range(10)]}

    with tempfile.TemporaryDirectory() as tmp:
        store = JSONFileStateStore(path=Path(tmp) / "state.json")
        sampler = CollisionVectorSampler(pools, store=store)

        draws = [sampler.draw("cultural") for _ in range(10)]
        assert sorted(draws) == sorted(pools["cultural"]), "First pass must cover the whole pool"
        assert len(set(draws)) == 10, "No repeats within a single pass"

        # 11th draw starts a new shuffled pass - still must be a valid pool member
        next_draw = sampler.draw("cultural")
        assert next_draw in pools["cultural"]

    print("✓ 10 draws from a 10-item pool covered every item with zero repeats\n")


def test_sampler_persists_across_instances():
    print("=" * 60)
    print("Test 2: Sampler state persists to disk across instances")
    print("=" * 60)

    pools = {"cultural": [f"item-{i}" for i in range(6)]}

    with tempfile.TemporaryDirectory() as tmp:
        store = JSONFileStateStore(path=Path(tmp) / "state.json")

        sampler_a = CollisionVectorSampler(pools, store=store)
        first_three = {sampler_a.draw("cultural") for _ in range(3)}

        # Simulate a process restart: fresh instance, same backing store
        sampler_b = CollisionVectorSampler(pools, store=store)
        next_three = {sampler_b.draw("cultural") for _ in range(3)}

        assert first_three.isdisjoint(next_three), "Second instance must not repeat first instance's draws"
        assert first_three | next_three == set(pools["cultural"]), "Together they exhaust the pool"

    print("✓ Bag state survived a simulated process restart with no repeats\n")


def test_real_pools_have_no_repeats_across_full_pass():
    print("=" * 60)
    print("Test 3: Real COLLISION_VECTORS pools - full pass, no repeats")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmp:
        store = JSONFileStateStore(path=Path(tmp) / "state.json")
        sampler = CollisionVectorSampler(collision_protocol.COLLISION_VECTORS, store=store)

        for category, options in collision_protocol.COLLISION_VECTORS.items():
            draws = [sampler.draw(category) for _ in range(len(options))]
            assert len(set(draws)) == len(options), f"{category}: expected {len(options)} unique draws, got {len(set(draws))}"
            print(f"  {category}: {len(options)} items, {len(set(draws))} unique draws - OK")

    print("✓ Every category cycles through its full pool with zero repeats\n")


def test_database_backed_store_round_trips():
    print("=" * 60)
    print("Test 4: DB-backed store persists across instances (production path)")
    print("=" * 60)

    from contextlib import contextmanager
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from web.models import Base
    from web.services import collision_state_store as store_module

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test_collision_state.db"
        engine = create_engine(f"sqlite:///{db_path}")
        Base.metadata.create_all(bind=engine)
        TestSessionLocal = sessionmaker(bind=engine)

        @contextmanager
        def fake_get_db_context():
            db = TestSessionLocal()
            try:
                yield db
                db.commit()
            finally:
                db.close()

        # Point the store at our isolated test DB instead of the real one
        original_get_db_context = store_module.get_db_context
        store_module.get_db_context = fake_get_db_context
        try:
            store_module.DatabaseVectorStateStore().save({"cultural": ["a", "b", "c"]})

            # Fresh instance, same backing DB - simulates a container restart
            loaded = store_module.DatabaseVectorStateStore().load()
            assert loaded == {"cultural": ["a", "b", "c"]}, "Bag state must round-trip through the DB"

            store_module.DatabaseVectorStateStore().save({"cultural": ["a"], "personal": ["x", "y"]})
            loaded2 = store_module.DatabaseVectorStateStore().load()
            assert loaded2 == {"cultural": ["a"], "personal": ["x", "y"]}, "Updates to existing + new categories must persist"
        finally:
            store_module.get_db_context = original_get_db_context

    print("✓ DatabaseVectorStateStore round-trips bag state through SQLAlchemy correctly\n")


def main():
    print("\n")
    print("=" * 60)
    print("COLLISION ENGINE FIX VERIFICATION")
    print("=" * 60)
    print()

    try:
        test_sampler_no_repeats_within_one_pass()
        test_sampler_persists_across_instances()
        test_real_pools_have_no_repeats_across_full_pass()
        test_database_backed_store_round_trips()

        print("=" * 60)
        print("ALL TESTS PASSED")
        print("=" * 60)
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

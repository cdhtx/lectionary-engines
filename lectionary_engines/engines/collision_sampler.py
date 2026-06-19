"""
Collision Vector Sampler

Plain random.choice() draws from a fixed pool produce repeats within a handful
of generations even with 30+ items per category (birthday-paradox effect) -
there's no memory of what was picked last time.

This shuffles each category's pool into a bag and draws without replacement,
reshuffling only once the bag is empty. That guarantees zero repeats for an
entire pass through the pool (30-39 generations per category here).

Storage is pluggable via VectorStateStore. The default JSONFileStateStore is
fine for local/CLI use, but it is NOT durable in production: the app
filesystem is ephemeral on Railway/Render (wiped on every redeploy and
container restart). The web app injects a database-backed store instead -
see web/services/collision_state_store.py.
"""

import json
import random
from pathlib import Path
from typing import Dict, List, Protocol

DEFAULT_STATE_PATH = Path(__file__).parent / ".collision_vector_state.json"


class VectorStateStore(Protocol):
    def load(self) -> Dict[str, List[str]]: ...
    def save(self, state: Dict[str, List[str]]) -> None: ...


class JSONFileStateStore:
    """Local-disk persistence. Good enough for CLI/standalone use; not durable
    across redeploys on ephemeral hosting - the web app uses a DB-backed store."""

    def __init__(self, path: Path = DEFAULT_STATE_PATH):
        self.path = path

    def load(self) -> Dict[str, List[str]]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def save(self, state: Dict[str, List[str]]) -> None:
        try:
            self.path.write_text(json.dumps(state), encoding="utf-8")
        except OSError:
            pass  # Best-effort persistence; in-memory sampling still works for this process


class CollisionVectorSampler:
    def __init__(self, vector_pools: Dict[str, List[str]], store: VectorStateStore = None):
        self.vector_pools = vector_pools
        self.store = store or JSONFileStateStore()
        self._bags: Dict[str, List[str]] = self._load_state()

    def _load_state(self) -> Dict[str, List[str]]:
        saved = self.store.load()
        bags = {}
        for category, options in self.vector_pools.items():
            # Drop any saved entries that no longer exist in the current pool
            # (handles pool edits between deploys without crashing)
            bags[category] = [item for item in saved.get(category, []) if item in options]
        return bags

    def _save_state(self) -> None:
        self.store.save(self._bags)

    def draw(self, category: str) -> str:
        """Draw a vector from a category without repeating until its pool is exhausted."""
        bag = self._bags.get(category) or []

        if not bag:
            bag = list(self.vector_pools[category])
            random.shuffle(bag)

        vector = bag.pop()
        self._bags[category] = bag
        self._save_state()
        return vector

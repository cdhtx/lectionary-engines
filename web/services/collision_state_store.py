"""
Database-backed persistence for the Collision engine's no-repeat vector sampler.

The app filesystem is ephemeral on Railway/Render (wiped on every redeploy and
container restart), so the sampler's bag state has to live in the DB - the
same place Studies/Users already persist - to actually survive across deploys.
"""

import json
from typing import Dict, List

from ..database import get_db_context
from ..models import CollisionVectorState


class DatabaseVectorStateStore:
    def load(self) -> Dict[str, List[str]]:
        with get_db_context() as db:
            rows = db.query(CollisionVectorState).all()
            return {row.category: json.loads(row.remaining_bag) for row in rows}

    def save(self, state: Dict[str, List[str]]) -> None:
        with get_db_context() as db:
            for category, bag in state.items():
                row = db.query(CollisionVectorState).filter_by(category=category).first()
                payload = json.dumps(bag)
                if row:
                    row.remaining_bag = payload
                else:
                    db.add(CollisionVectorState(category=category, remaining_bag=payload))

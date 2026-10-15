"""
Generate one signal right now, ignoring the two-day schedule.

Usage: python -m web.scripts.generate_signal
Prints the new signal, or says nothing usable was produced (see the log).
"""

import logging

from web.database import SessionLocal, init_db
from web.services.signal_generator import generate_signal
from web.services.signals_scheduler import _default_client


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    init_db()
    db = SessionLocal()
    try:
        signal = generate_signal(db, _default_client())
        if signal is None:
            print("No usable signal was produced. See the log above.")
            return 1
        print(f"\n{signal.title}  [{signal.modern_illustration_category}]  model={signal.model}")
        print(f"tokens in/out: {signal.input_tokens}/{signal.output_tokens}  searches: {signal.search_count}\n")
        print(f"Signal detected: {signal.signal_detected}\n")
        print(f"Connection: {signal.connection}\n")
        print(f"Nature of the connection: {signal.nature_of_connection}\n")
        print(f"Intratextual: {signal.intratextual}\n")
        print(f"Modern illustration: {signal.modern_illustration}\n")
        for b in signal.dig_deeper_list:
            print(f"  - {b['title']} by {b['author']} ({b['kind']}): {b['why']}")
        for s in signal.sources_list:
            print(f"  source: {s['title']} {s['url']}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

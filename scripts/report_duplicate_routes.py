from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app


def main() -> int:
    app = create_app()
    seen = defaultdict(list)

    for rule in app.url_map.iter_rules():
        methods = sorted((rule.methods or set()) - {"HEAD", "OPTIONS"})
        for method in methods:
            seen[(rule.rule, method)].append(rule.endpoint)

    duplicates = {
        key: endpoints
        for key, endpoints in sorted(seen.items())
        if len(set(endpoints)) > 1
    }

    if not duplicates:
        print("Duplicate route visibility: no duplicate routes found.")
        return 0

    print("Duplicate route visibility report (informational only):")
    for (rule, method), endpoints in duplicates.items():
        endpoint_list = ", ".join(sorted(set(endpoints)))
        print(f"{method} {rule}: {endpoint_list}")
    print("Duplicate routes are expected during the legacy/modular strangler migration.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

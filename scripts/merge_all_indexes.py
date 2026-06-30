"""Merge all knowledge base indexes into a global index for multi-KB support."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from finlongrag.core.config import Settings
from finlongrag.index.merge import merge_global_indexes
from finlongrag.storage.knowledge_repository import create_knowledge_repository


def main() -> None:
    print("=" * 60)
    print("Merging All Knowledge Base Indexes")
    print("=" * 60)

    settings = Settings.from_file()
    repo = create_knowledge_repository(settings.database_url)
    result = merge_global_indexes(settings, repo)

    print(f"\nResult: {result}")
    if result.get("status") == "ok":
        print("\n[SUCCESS] Global indexes created. Restart the service to reload them.")
    else:
        print("\n[SKIPPED] No chunks available to merge.")


if __name__ == "__main__":
    main()

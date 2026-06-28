"""查看知识库名称和 ID 映射"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from finlongrag.core.config import Settings
from finlongrag.storage.knowledge_repository import create_knowledge_repository


def main():
    print("=" * 70)
    print("知识库名称与 ID 映射")
    print("=" * 70)

    settings = Settings.from_file()
    repo = create_knowledge_repository(settings.database_url)
    kbs = repo.list_knowledge_bases()

    for kb in kbs:
        print(f"\n名称: {kb.name}")
        print(f"  ID: {kb.kb_id}")
        print(f"  文档数: {kb.metadata.get('document_count', 0)}")


if __name__ == "__main__":
    main()

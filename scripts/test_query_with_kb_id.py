"""直接测试带 kb_id 的查询，验证知识库隔离。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from finlongrag.core.config import Settings
from finlongrag.service.pipeline import FinLongRAGPipeline


def main():
    """测试带 kb_id 的查询。"""
    print("=" * 70)
    print("测试知识库隔离查询")
    print("=" * 70)

    settings = Settings.from_file()
    pipeline = FinLongRAGPipeline(settings)

    # 两个知识库 ID（从验证脚本获得）
    kb_finance = "f066ed944b5240dd9e2a734ad122fc4a"  # 金融库 (421 chunks)
    kb_manage = "e4dbce7568494b52be637e6e47c2bc47"   # 管理库 (71 chunks)

    test_query = "什么是犹豫期"

    print(f"\n测试查询: {test_query}")
    print("=" * 70)

    # 测试 1: 在金融库查询
    print(f"\n[测试 1] 在金融库查询 (KB: {kb_finance})")
    print("-" * 70)
    result1 = pipeline.ask(test_query, kb_id=kb_finance)
    print(f"  答案: {result1.answer[:100]}...")
    print(f"  证据数量: {len(result1.evidence)}")
    for i, ev in enumerate(result1.evidence[:3]):
        kb_id = ev.metadata.get("kb_id", "MISSING")[:16]
        doc_id = ev.doc_id
        print(f"    [{i+1}] doc={doc_id}, kb={kb_id}...")

    # 测试 2: 在管理库查询
    print(f"\n[测试 2] 在管理库查询 (KB: {kb_manage})")
    print("-" * 70)
    result2 = pipeline.ask(test_query, kb_id=kb_manage)
    print(f"  答案: {result2.answer[:100]}...")
    print(f"  证据数量: {len(result2.evidence)}")
    for i, ev in enumerate(result2.evidence[:3]):
        kb_id = ev.metadata.get("kb_id", "MISSING")[:16]
        doc_id = ev.doc_id
        print(f"    [{i+1}] doc={doc_id}, kb={kb_id}...")

    # 测试 3: 不指定 KB（全局搜索）
    print(f"\n[测试 3] 不指定 KB (全局搜索)")
    print("-" * 70)
    result3 = pipeline.ask(test_query, kb_id=None)
    print(f"  答案: {result3.answer[:100]}...")
    print(f"  证据数量: {len(result3.evidence)}")
    kb_distribution = {}
    for ev in result3.evidence:
        kb_id = ev.metadata.get("kb_id", "MISSING")
        kb_distribution[kb_id] = kb_distribution.get(kb_id, 0) + 1
    for kb_id, count in kb_distribution.items():
        print(f"    KB {kb_id[:16]}...: {count} 个证据")

    print("\n" + "=" * 70)
    print("[完成]")
    print("=" * 70)


if __name__ == "__main__":
    main()

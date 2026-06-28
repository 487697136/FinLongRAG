"""测试多库融合时的检索结果分布"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from finlongrag.core.config import Settings
from finlongrag.service.pipeline import FinLongRAGPipeline


def main():
    print("=" * 70)
    print("测试多知识库融合检索")
    print("=" * 70)

    settings = Settings.from_file()
    pipeline = FinLongRAGPipeline(settings)

    # 两个知识库 ID
    kb_finance = "f066ed944b5240dd9e2a734ad122fc4a"  # 金融库
    kb_manage = "e4dbce7568494b52be637e6e47c2bc47"   # 管理库

    # 测试融合查询
    test_query = "我想知道平安 e 生保住院 7.0 医疗保险 A 款条款的投保年龄和私募投资基金信息披露监督管理办法的时间日期"

    print(f"\n测试查询: {test_query}")
    print("=" * 70)

    # 多库融合模式
    print(f"\n[多库融合] 金融库 + 管理库")
    print("-" * 70)
    result = pipeline.ask(test_query, kb_ids=[kb_finance, kb_manage])

    print(f"\n答案前 200 字: {result.answer[:200]}...")
    print(f"\n证据数量: {len(result.evidence)}")

    # 统计 KB 分布
    kb_distribution = {}
    for ev in result.evidence:
        kb_id = ev.metadata.get("kb_id", "UNKNOWN")
        kb_name = "金融库" if kb_id == kb_finance else ("管理库" if kb_id == kb_manage else "未知")
        doc_id = ev.doc_id
        key = f"{kb_name} - {doc_id}"
        kb_distribution[key] = kb_distribution.get(key, 0) + 1

    print("\n证据来源分布:")
    for key, count in sorted(kb_distribution.items()):
        print(f"  {key}: {count} 个证据")

    print("\n详细证据列表（前 10 个）:")
    for i, ev in enumerate(result.evidence[:10]):
        kb_id = ev.metadata.get("kb_id", "UNKNOWN")
        kb_name = "金融" if kb_id == kb_finance else ("管理" if kb_id == kb_manage else "未知")
        score = ev.score
        text_preview = ev.evidence_text[:80].replace("\n", " ")
        print(f"  [{i+1}] {kb_name}库 | score={score:.3f} | {text_preview}...")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()

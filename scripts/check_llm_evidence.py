"""检查传递给 LLM 的证据内容"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from finlongrag.core.config import Settings
from finlongrag.service.pipeline import FinLongRAGPipeline


def main():
    print("=" * 70)
    print("检查多库融合时传递给 LLM 的证据")
    print("=" * 70)

    settings = Settings.from_file()
    pipeline = FinLongRAGPipeline(settings)

    # 两个知识库 ID
    kb_finance = "f066ed944b5240dd9e2a734ad122fc4a"  # 金融库
    kb_manage = "e4dbce7568494b52be637e6e47c2bc47"   # 管理库

    # 测试查询
    query = "我想知道平安 e 生保住院 7.0 医疗保险 A 款条款的投保年龄和私募投资基金信息披露监督管理办法的时间日期"

    print(f"\n查询: {query}")
    print("=" * 70)

    # 多库融合检索
    result = pipeline.ask(query, kb_ids=[kb_finance, kb_manage])

    print(f"\n答案: {result.answer[:300]}...")
    print(f"\n证据数量: {len(result.evidence)}")

    # 统计证据来源分布
    kb_dist = {}
    for ev in result.evidence:
        kb_id = ev.metadata.get("kb_id", "UNKNOWN")
        kb_name = "金融" if kb_id == kb_finance else ("管理" if kb_id == kb_manage else "未知")
        kb_dist[kb_name] = kb_dist.get(kb_name, 0) + 1

    print(f"\n证据来源分布: {kb_dist}")

    print("\n详细证据列表:")
    for i, ev in enumerate(result.evidence):
        kb_id = ev.metadata.get("kb_id", "UNKNOWN")
        kb_name = "金融" if kb_id == kb_finance else ("管理" if kb_id == kb_manage else "未知")
        doc_id = ev.doc_id
        score = ev.score
        text_preview = ev.evidence_text[:100].replace("\n", " ")
        print(f"  [{i+1}] {kb_name}库 | doc={doc_id[:20]}... | score={score:.4f}")
        print(f"      {text_preview}...")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()

"""详细检查多库融合时的原始检索结果"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from finlongrag.core.config import Settings
from finlongrag.core.schema import Question
from finlongrag.retrieval.retriever import Retriever
from finlongrag.index.bm25 import BM25FIndex
from finlongrag.retrieval.channels import BM25SearchChannel


def main():
    print("=" * 70)
    print("详细检查多库融合检索")
    print("=" * 70)

    settings = Settings.from_file()

    # 加载全局索引
    index_path = settings.index_dir / "bm25_index_global.pkl"
    bm25_index = BM25FIndex.load(index_path)

    print(f"\n全局索引总 chunks: {len(bm25_index.chunks)}")

    # 两个知识库 ID
    kb_finance = "f066ed944b5240dd9e2a734ad122fc4a"  # 金融库
    kb_manage = "e4dbce7568494b52be637e6e47c2bc47"   # 管理库

    # 测试查询
    query = "私募投资基金信息披露监督管理办法的时间日期"

    print(f"\n查询: {query}")
    print("=" * 70)

    # 单独检索每个库
    print("\n[1] 只在金融库检索 (top_k=20)")
    results_finance = bm25_index.search(query, top_k=20, kb_id=kb_finance)
    print(f"  结果数: {len(results_finance)}")
    for i, r in enumerate(results_finance[:5]):
        print(f"    [{i+1}] score={r.score:.4f} | {r.evidence_text[:60]}...")

    print("\n[2] 只在管理库检索 (top_k=20)")
    results_manage = bm25_index.search(query, top_k=20, kb_id=kb_manage)
    print(f"  结果数: {len(results_manage)}")
    for i, r in enumerate(results_manage[:5]):
        print(f"    [{i+1}] score={r.score:.4f} | {r.evidence_text[:60]}...")

    print("\n[3] 融合两个库检索 (top_k=20)")
    results_fusion = bm25_index.search(query, top_k=20, kb_ids=[kb_finance, kb_manage])
    print(f"  结果数: {len(results_fusion)}")

    kb_dist = {}
    for r in results_fusion:
        kb_id = r.metadata.get("kb_id", "UNKNOWN")
        kb_name = "金融" if kb_id == kb_finance else ("管理" if kb_id == kb_manage else "未知")
        kb_dist[kb_name] = kb_dist.get(kb_name, 0) + 1

    print(f"\n  KB 分布: {kb_dist}")
    print("\n  前 10 个结果:")
    for i, r in enumerate(results_fusion[:10]):
        kb_id = r.metadata.get("kb_id", "UNKNOWN")
        kb_name = "金融" if kb_id == kb_finance else ("管理" if kb_id == kb_manage else "未知")
        print(f"    [{i+1}] {kb_name}库 | score={r.score:.4f} | {r.evidence_text[:60]}...")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()

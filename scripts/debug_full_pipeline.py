"""完整调试多库融合流程"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from finlongrag.core.config import Settings
from finlongrag.service.pipeline import FinLongRAGPipeline

# Patch retriever to add debug output
original_search_channels = None

def debug_search_channels(self, question, queries, *, filter_doc_ids, top_k_per_query=None, fused_top_k=None, source):
    print(f"\n=== _search_channels called ===")
    print(f"queries: {queries}")
    print(f"question.metadata: {question.metadata}")

    result = original_search_channels(self, question, queries,
                                       filter_doc_ids=filter_doc_ids,
                                       top_k_per_query=top_k_per_query,
                                       fused_top_k=fused_top_k,
                                       source=source)

    kb_dist = {}
    for r in result:
        kb_id = r.metadata.get('kb_id', 'UNKNOWN')
        kb_dist[kb_id[:10]] = kb_dist.get(kb_id[:10], 0) + 1

    print(f"Result count: {len(result)}")
    print(f"KB distribution: {kb_dist}")

    return result


def main():
    settings = Settings.from_file()
    pipeline = FinLongRAGPipeline(settings)

    # Patch
    global original_search_channels
    from finlongrag.retrieval import retriever as retriever_module
    original_search_channels = retriever_module.Retriever._search_channels
    retriever_module.Retriever._search_channels = debug_search_channels

    kb_f = 'f066ed944b5240dd9e2a734ad122fc4a'
    kb_m = 'e4dbce7568494b52be637e6e47c2bc47'

    query = '我想知道平安 e 生保住院 7.0 医疗保险 A 款条款的投保年龄和私募投资基金信息披露监督管理办法的时间日期'

    print("=" * 70)
    print("测试多库融合")
    print("=" * 70)
    print(f"Query: {query}")
    print(f"KB IDs: {[kb_f, kb_m]}")

    result = pipeline.ask(query, kb_ids=[kb_f, kb_m])

    print("\n" + "=" * 70)
    print(f"Final evidence count: {len(result.evidence)}")

    kb_dist = {}
    for ev in result.evidence:
        kb_id = ev.metadata.get('kb_id', 'UNKNOWN')
        kb_name = 'Finance' if kb_id == kb_f else ('Management' if kb_id == kb_m else 'Unknown')
        kb_dist[kb_name] = kb_dist.get(kb_name, 0) + 1

    print(f"Final KB distribution: {kb_dist}")


if __name__ == "__main__":
    main()

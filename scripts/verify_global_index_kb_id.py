"""验证全局索引中的 chunks 是否包含 kb_id。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from finlongrag.core.config import Settings
from finlongrag.index.bm25 import BM25FIndex


def main():
    """验证全局 BM25 索引中每个 chunk 是否包含 kb_id。"""
    print("=" * 70)
    print("验证全局索引 KB ID 分布")
    print("=" * 70)

    settings = Settings.from_file()
    global_index_path = settings.index_dir / "bm25_index_global.pkl"

    if not global_index_path.exists():
        print(f"\n[ERROR] 全局索引不存在: {global_index_path}")
        print("请先运行: python scripts/merge_all_indexes.py")
        return

    print(f"\n[OK] 加载全局索引: {global_index_path}")
    index = BM25FIndex.load(global_index_path)
    print(f"   总 chunks: {len(index.chunks)}")

    # 统计每个 KB 的 chunks
    kb_stats = {}
    missing_kb_id = []

    for i, chunk in enumerate(index.chunks):
        kb_id = chunk.metadata.get("kb_id")
        if kb_id:
            kb_stats[kb_id] = kb_stats.get(kb_id, 0) + 1
        else:
            missing_kb_id.append((i, chunk.chunk_id, chunk.doc_id))

    print("\n" + "=" * 70)
    print("KB ID 分布统计")
    print("=" * 70)

    if kb_stats:
        for kb_id, count in sorted(kb_stats.items(), key=lambda x: x[1], reverse=True):
            print(f"  KB: {kb_id[:16]}... → {count:4d} chunks")
    else:
        print("  [ERROR] 没有任何 chunk 包含 kb_id！")

    if missing_kb_id:
        print(f"\n[WARNING] 发现 {len(missing_kb_id)} 个 chunks 缺少 kb_id：")
        for i, chunk_id, doc_id in missing_kb_id[:10]:
            print(f"     [{i}] {chunk_id[:16]}... (doc: {doc_id})")
        if len(missing_kb_id) > 10:
            print(f"     ... 还有 {len(missing_kb_id) - 10} 个")
    else:
        print("\n[OK] 所有 chunks 都包含 kb_id！")

    # 测试 BM25 搜索过滤
    print("\n" + "=" * 70)
    print("测试 BM25 搜索过滤")
    print("=" * 70)

    test_kb_id = list(kb_stats.keys())[0] if kb_stats else None
    if test_kb_id:
        print(f"\n测试查询（限制到 KB: {test_kb_id[:16]}...）")
        results = index.search("测试查询", top_k=10, kb_id=test_kb_id)
        print(f"  返回结果: {len(results)} 个")
        for r in results[:5]:
            result_kb_id = r.metadata.get("kb_id", "MISSING")
            match = "[OK]" if result_kb_id == test_kb_id else "[FAIL]"
            print(f"    {match} {r.chunk_id[:16]}... (KB: {result_kb_id[:16]}...)")

        # 测试无过滤
        print(f"\n测试查询（无 KB 过滤）")
        results_all = index.search("测试查询", top_k=10)
        print(f"  返回结果: {len(results_all)} 个")
        kb_distribution = {}
        for r in results_all:
            result_kb_id = r.metadata.get("kb_id", "MISSING")
            kb_distribution[result_kb_id] = kb_distribution.get(result_kb_id, 0) + 1
        for kb_id, count in kb_distribution.items():
            print(f"    KB {kb_id[:16]}...: {count} 个")

    print("\n" + "=" * 70)
    print("[完成]")
    print("=" * 70)


if __name__ == "__main__":
    main()

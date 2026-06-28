"""验证后端是否加载了修复后的代码"""

import sys
from pathlib import Path
import inspect

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from finlongrag.retrieval.retriever import Retriever
from finlongrag.reasoning.verifier import ClaimVerifier

def main():
    print("=" * 70)
    print("验证代码是否包含修复")
    print("=" * 70)

    # 检查 Retriever.retrieve_queries 签名
    print("\n[1] Retriever.retrieve_queries() 签名:")
    sig = inspect.signature(Retriever.retrieve_queries)
    params = list(sig.parameters.keys())
    print(f"    参数: {params}")

    if 'metadata' in params:
        print("    ✅ 包含 'metadata' 参数 - 修复已应用")
    else:
        print("    ❌ 缺少 'metadata' 参数 - 修复未应用！")

    # 检查 ClaimVerifier.verify 签名
    print("\n[2] ClaimVerifier.verify() 签名:")
    sig = inspect.signature(ClaimVerifier.verify)
    params = list(sig.parameters.keys())
    print(f"    参数: {params}")

    if 'metadata' in params:
        print("    ✅ 包含 'metadata' 参数 - 修复已应用")
    else:
        print("    ❌ 缺少 'metadata' 参数 - 修复未应用！")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()

"""API 测试脚本 - 验证多知识库隔离功能"""

import requests
import json
import time

BASE_URL = "http://127.0.0.1:7860/api/v1"

def login():
    """登录获取 token"""
    response = requests.post(
        f"{BASE_URL}/auth/login",
        data={"username": "admin", "password": "finlongrag"}
    )
    if response.status_code == 200:
        token = response.json()["data"]["access_token"]
        print(f"[OK] 登录成功")
        return token
    else:
        print(f"[FAIL] 登录失败: {response.text}")
        return None


def create_knowledge_base(token, name, description):
    """创建知识库"""
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.post(
        f"{BASE_URL}/knowledge-bases/",
        headers=headers,
        json={"name": name, "description": description}
    )
    if response.status_code == 200:
        kb = response.json()["data"]
        print(f"[OK] 创建知识库: {name} (ID: {kb['kb_id']})")
        return kb
    else:
        print(f"[FAIL] 创建失败: {response.text}")
        return None


def list_knowledge_bases(token):
    """列出所有知识库"""
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(f"{BASE_URL}/knowledge-bases/", headers=headers)
    if response.status_code == 200:
        kbs = response.json()["data"]
        print(f"[OK] 共有 {len(kbs)} 个知识库")
        for kb in kbs:
            print(f"  - {kb['name']} (ID: {kb['kb_id']})")
        return kbs
    else:
        print(f"[FAIL] 获取失败: {response.text}")
        return []


def get_kb_stats(token, kb_id):
    """获取知识库统计信息"""
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(
        f"{BASE_URL}/knowledge-bases/{kb_id}/statistics",
        headers=headers
    )
    if response.status_code == 200:
        stats = response.json()["data"]
        print(f"[OK] 知识库统计:")
        print(f"  - 文档数: {stats['document_count']}")
        print(f"  - Chunks: {stats['chunks']}")
        print(f"  - 已初始化: {stats['initialized']}")
        return stats
    else:
        print(f"[FAIL] 获取统计失败: {response.text}")
        return None


def delete_knowledge_base(token, kb_id):
    """删除知识库"""
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.delete(
        f"{BASE_URL}/knowledge-bases/{kb_id}",
        headers=headers
    )
    if response.status_code == 200:
        print(f"[OK] 删除知识库成功")
        return True
    else:
        print(f"[FAIL] 删除失败: {response.text}")
        return False


def main():
    print("=" * 60)
    print("多知识库隔离功能 - API 测试")
    print("=" * 60)

    # 登录
    token = login()
    if not token:
        return

    # 测试 1: 创建两个知识库
    print("\n[Test 1] 创建两个知识库...")
    kb1 = create_knowledge_base(token, "测试知识库A", "用于测试隔离功能")
    kb2 = create_knowledge_base(token, "测试知识库B", "用于测试隔离功能")

    if not kb1 or not kb2:
        print("[FAIL] 创建知识库失败")
        return

    # 测试 2: 列出所有知识库
    print("\n[Test 2] 列出所有知识库...")
    kbs = list_knowledge_bases(token)

    # 测试 3: 获取每个知识库的统计信息
    print("\n[Test 3] 获取知识库统计信息...")
    print(f"\n知识库 A:")
    get_kb_stats(token, kb1["kb_id"])

    print(f"\n知识库 B:")
    get_kb_stats(token, kb2["kb_id"])

    # 测试 4: 清理 - 删除测试知识库
    print("\n[Test 4] 清理测试数据...")
    delete_knowledge_base(token, kb1["kb_id"])
    delete_knowledge_base(token, kb2["kb_id"])

    print("\n" + "=" * 60)
    print("[PASS] API 测试完成")
    print("=" * 60)
    print("\n后续测试:")
    print("1. 上传文档到知识库 A")
    print("2. 上传文档到知识库 B")
    print("3. 在知识库 A 中问答，验证只返回 A 的结果")
    print("4. 在知识库 B 中问答，验证只返回 B 的结果")
    print("\n这些需要在 Web 界面中完成")


if __name__ == "__main__":
    main()

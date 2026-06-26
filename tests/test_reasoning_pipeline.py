from finlongrag.core.schema import Chunk, Question, TokenUsage
from finlongrag.index.bm25 import BM25FIndex
from finlongrag.reasoning.llm import LLMResponse
from finlongrag.reasoning.pipeline import ReasoningPipeline
from finlongrag.retrieval.retriever import Retriever


class FakeLLM:
    def chat(self, messages, *, max_tokens=None, temperature=None):
        payload = "\n".join(message["content"] for message in messages)
        if "净利润出现下滑" in payload:
            text = '{"label":"false","confidence":0.82,"citations":["E1"],"reason":"证据显示净利润为增长而非下滑"}'
        elif "营业收入较 2024 年实现增长" in payload:
            text = '{"label":"true","confidence":0.91,"citations":["E1"],"reason":"2025年营业收入高于2024年"}'
        else:
            text = '{"label":"insufficient","confidence":0.0,"citations":[],"reason":"证据不足"}'
        return LLMResponse(text=text, usage=TokenUsage(prompt_tokens=10, completion_tokens=5))


def test_claim_pipeline_assembles_multi_answer():
    chunks = [
        Chunk(
            chunk_id="c1",
            doc_id="byd_2025",
            domain="financial_reports",
            text="营业收入 2025年 120亿元，2024年 100亿元。归属于上市公司股东的净利润 2025年 30亿元，2024年 20亿元。",
            page=1,
            section="主要财务指标",
            numbers=["2025年", "120亿元", "2024年", "100亿元", "30亿元", "20亿元"],
            metadata={"title": "BYD", "extra_index_fields": ["营业收入", "净利润"]},
        )
    ]
    retriever = Retriever(BM25FIndex.build(chunks), fused_top_k=8, top_k_per_query=8)
    pipeline = ReasoningPipeline(retriever, FakeLLM(), evidence_per_claim=2)
    question = Question(
        qid="q1",
        domain="financial_reports",
        question="根据年度报告，下列关于公司经营业绩变化的描述中，哪些是准确的？",
        options={
            "A": "2025 年营业收入较 2024 年实现增长",
            "B": "2025 年归属于上市公司股东的净利润出现下滑",
        },
        answer_format="multi",
        doc_ids=["byd_2025"],
    )

    result = pipeline.answer(question)

    assert result.answer == "A"
    assert len(result.verdicts) == 2
    assert result.token_usage.total_tokens == 30


from finlongrag.core.schema import Chunk, Question, RetrievalResult, TokenUsage
from finlongrag.index.bm25 import BM25FIndex
from finlongrag.reasoning.llm import LLMResponse, LLMStreamChunk
from finlongrag.reasoning.pipeline import ReasoningPipeline
from finlongrag.retrieval.rerank import PassThroughReranker
from finlongrag.retrieval.retriever import Retriever


class FakeLLM:
    def chat(self, messages, *, max_tokens=None, temperature=None):
        payload = "\n".join(message["content"] for message in messages)
        if "待核验陈述" in payload or "claim" in payload.lower():
            if "净利润出现下滑" in payload:
                text = '{"label":"false","confidence":0.82,"citations":["E1"],"reason":"证据显示净利润为增长"}'
            elif "营业收入较 2024 年实现增长" in payload:
                text = '{"label":"true","confidence":0.91,"citations":["E1"],"reason":"2025年营业收入高于2024年"}'
            else:
                text = '{"label":"insufficient","confidence":0.0,"citations":[],"reason":"证据不足"}'
        else:
            text = "根据证据 [E1]，文档描述了主要财务指标。[E1]"
        return LLMResponse(text=text, usage=TokenUsage(prompt_tokens=10, completion_tokens=5))

    def chat_stream(self, messages, *, max_tokens=None, temperature=None):
        response = self.chat(messages, max_tokens=max_tokens, temperature=temperature)
        for char in response.text:
            yield LLMStreamChunk(content=char)
        yield LLMStreamChunk(content="", finish_reason="stop")


def _sample_chunks() -> list[Chunk]:
    return [
        Chunk(
            chunk_id="c1",
            doc_id="demo_report",
            domain="reports",
            text="[主要财务指标]\n营业收入 2025年 120亿元，2024年 100亿元。归属于上市公司股东的净利润 2025年 30亿元，2024年 20亿元。",
            page=1,
            section="主要财务指标",
            numbers=["2025年", "120亿元", "2024年", "100亿元", "30亿元", "20亿元"],
            metadata={"title": "Demo", "extra_index_fields": ["主要财务指标", "2025年", "120亿元"]},
        )
    ]


def test_open_rag_pipeline_returns_grounded_answer():
    retriever = Retriever(BM25FIndex.build(_sample_chunks()), fused_top_k=8, top_k_per_query=8)
    pipeline = ReasoningPipeline(
        retriever, FakeLLM(), evidence_top_k=4, evidence_reranker=PassThroughReranker()
    )
    question = Question(
        qid="q-open",
        domain="reports",
        question="2025年营业收入是多少？",
        answer_format="open",
        doc_ids=["demo_report"],
    )

    result = pipeline.answer(question)

    assert result.evidence
    assert result.answer
    assert result.metadata["strategy"] == "agentic_rag"
    assert result.metadata["gated"] is False


def test_open_rag_pipeline_streams_tokens():
    retriever = Retriever(BM25FIndex.build(_sample_chunks()), fused_top_k=8, top_k_per_query=8)
    pipeline = ReasoningPipeline(
        retriever, FakeLLM(), evidence_top_k=4, evidence_reranker=PassThroughReranker()
    )
    question = Question(
        qid="q-stream",
        domain="reports",
        question="2025年营业收入是多少？",
        answer_format="open",
        doc_ids=["demo_report"],
    )

    chunks = []
    final = None
    for event in pipeline.answer_stream(question):
        if event.content:
            chunks.append(event.content)
        if event.done:
            final = event.result

    assert chunks
    assert final is not None
    assert final.answer
    assert "".join(chunks).startswith("根据证据")


def test_claim_pipeline_assembles_multi_answer():
    retriever = Retriever(BM25FIndex.build(_sample_chunks()), fused_top_k=8, top_k_per_query=8)
    pipeline = ReasoningPipeline(
        retriever, FakeLLM(), evidence_per_claim=2, evidence_reranker=PassThroughReranker()
    )
    question = Question(
        qid="q1",
        domain="reports",
        question="根据年度报告，下列关于公司经营业绩变化的描述中，哪些是准确的？",
        options={
            "A": "2025 年营业收入较 2024 年实现增长",
            "B": "2025 年归属于上市公司股东的净利润出现下滑",
        },
        answer_format="multi",
        doc_ids=["demo_report"],
    )

    result = pipeline.answer(question)

    assert result.answer == "A"
    assert len(result.verdicts) == 2
    assert result.token_usage.total_tokens == 30

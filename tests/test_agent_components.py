from finlongrag.agent.memory import WorkingMemory
from finlongrag.agent.planner import AgentPlanner
from finlongrag.agent.router import AgentRouter, RouteType
from finlongrag.core.schema import ClaimVerdict, Question, RetrievalResult


def test_router_and_planner_for_structured_question():
    question = Question(
        qid="q1",
        question="下列说法哪些正确？",
        options={"A": "正确", "B": "错误"},
        answer_format="multi",
    )

    route = AgentRouter().decide(question)
    plan = AgentPlanner().build(question, route)

    assert route.route == RouteType.STRUCTURED
    assert [step.action for step in plan.steps] == ["claim_verification"]


def test_rag_plan_matches_executor_handlers():
    question = Question(qid="q2", question="文档主要内容是什么？", answer_format="open")
    route = AgentRouter().decide(question)
    plan = AgentPlanner().build(question, route)

    assert route.route == RouteType.RAG
    assert plan.step_actions() == [
        "rewrite_query",
        "hybrid_retrieve",
        "rerank_evidence",
        "select_evidence",
        "assess_evidence",
        "generate_answer",
        "validate_citations",
    ]


def test_working_memory_keeps_high_signal_facts_after_compression():
    memory = WorkingMemory("q1", "question", max_facts=3)
    for index in range(6):
        memory.add_fact(f"普通事实 {index}")
    memory.add_fact("营业收入 2025年 120亿元")
    memory.add_verdict(
        ClaimVerdict(
            claim_id="q1:A",
            option_key="A",
            label="true",
            confidence=0.9,
            evidence=[
                RetrievalResult(
                    chunk_id="c1",
                    doc_id="d1",
                    domain="financial_reports",
                    evidence_text="营业收入 2025年 120亿元",
                    score=1.0,
                    source="test",
                    query="营业收入",
                    metadata={"numbers": ["2025年", "120亿元"], "page": 1, "section": "财务指标"},
                )
            ],
            reason="证据支持",
        )
    )

    summary = memory.summary()

    assert "营业收入" in summary
    assert len(memory.facts) <= 3

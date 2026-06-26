from finlongrag.core.schema import AnswerResult, TokenUsage
from finlongrag.eval.submission import summarize_usage


def test_summarize_usage_adds_all_results():
    results = [
        AnswerResult(qid="q1", answer="A", domain="regulatory", answer_format="mcq", token_usage=TokenUsage(1, 2)),
        AnswerResult(qid="q2", answer="BD", domain="research", answer_format="multi", token_usage=TokenUsage(3, 4)),
    ]

    usage = summarize_usage(results)

    assert usage.prompt_tokens == 4
    assert usage.completion_tokens == 6
    assert usage.total_tokens == 10


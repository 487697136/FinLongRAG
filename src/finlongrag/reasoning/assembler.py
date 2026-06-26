"""Answer synthesis from claim verdicts."""

from __future__ import annotations

from finlongrag.core.schema import ClaimVerdict, Question

TRUE_WORDS = ("正确", "对", "成立", "符合", "是", "真")


class AnswerAssembler:
    def assemble(self, question: Question, verdicts: list[ClaimVerdict]) -> tuple[str, float]:
        if question.answer_format == "multi":
            return self._multi(question, verdicts)
        if question.answer_format == "mcq":
            return self._mcq(question, verdicts)
        if question.answer_format == "tf":
            return self._tf(question, verdicts)
        return "", 0.0

    def _multi(self, question: Question, verdicts: list[ClaimVerdict]) -> tuple[str, float]:
        accepted = sorted(v.option_key for v in verdicts if v.label == "true" and v.option_key in question.options)
        if accepted:
            confidence = sum(v.confidence for v in verdicts if v.option_key in accepted) / len(accepted)
            return "".join(accepted), confidence
        selected = self._highest_confidence_option(question, verdicts)
        return selected, 0.0

    def _mcq(self, question: Question, verdicts: list[ClaimVerdict]) -> tuple[str, float]:
        true_verdicts = [v for v in verdicts if v.label == "true" and v.option_key in question.options]
        pool = true_verdicts or [v for v in verdicts if v.option_key in question.options]
        if not pool:
            return "A", 0.0
        best = max(pool, key=lambda item: item.confidence)
        return best.option_key, best.confidence if true_verdicts else 0.0

    def _tf(self, question: Question, verdicts: list[ClaimVerdict]) -> tuple[str, float]:
        true_letter, false_letter = self._tf_letters(question)
        if not verdicts or verdicts[0].label == "insufficient":
            return true_letter, 0.0
        return (true_letter, verdicts[0].confidence) if verdicts[0].label == "true" else (false_letter, verdicts[0].confidence)

    @staticmethod
    def _highest_confidence_option(question: Question, verdicts: list[ClaimVerdict]) -> str:
        pool = [v for v in verdicts if v.option_key in question.options]
        if not pool:
            return "A"
        return max(pool, key=lambda item: item.confidence).option_key

    @staticmethod
    def _tf_letters(question: Question) -> tuple[str, str]:
        true_letter, false_letter = "A", "B"
        for letter, text in question.options.items():
            if any(word in text for word in TRUE_WORDS):
                true_letter = letter
            else:
                false_letter = letter
        return true_letter, false_letter

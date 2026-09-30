from app.providers.ai_provider import AIProviderError


QUESTION_INSTRUCTION = (
    "Answer only from the supplied News History context. If the context does not support "
    "the answer, explicitly say that the available sources do not provide enough information. "
    "Do not invent information and include supporting article IDs when possible."
)


class QuestionAnswerService:
    def __init__(self, ai_provider):
        self.ai_provider = ai_provider

    @staticmethod
    def _extract_id(item):
        if isinstance(item, dict):
            return item.get("article_id")
        return getattr(item, "article_id", None)

    def answer(self, question, context):
        if not isinstance(question, str) or not question.strip():
            return {
                "success": False,
                "error": "Question cannot be empty.",
                "supporting_article_ids": [],
            }
        try:
            result = self.ai_provider.answer(QUESTION_INSTRUCTION, context, question.strip())
        except (AIProviderError, TimeoutError, OSError):
            return {
                "success": False,
                "error": "Answer temporarily unavailable.",
                "supporting_article_ids": [],
            }
        if not isinstance(result, dict) or not result.get("answer"):
            return {
                "success": False,
                "error": "Answer temporarily unavailable.",
                "supporting_article_ids": [],
            }

        # Fabricated-source prevention: ensure supporting IDs actually exist in context
        valid_ids = {
            self._extract_id(a)
            for a in context.get("articles", [])
            if self._extract_id(a) is not None
        }
        raw_ids = result.get("supporting_article_ids", [])
        verified_ids = [aid for aid in raw_ids if aid in valid_ids]

        return {
            "success": True,
            "answer": result["answer"],
            "supporting_article_ids": verified_ids,
            "automatic": True,
            "provider": self.ai_provider.name,
        }

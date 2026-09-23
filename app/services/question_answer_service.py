from app.providers.ai_provider import AIProviderError


QUESTION_INSTRUCTION = (
    "Answer only from the supplied News History context. If the context does not support "
    "the answer, explicitly say that the available sources do not provide enough information. "
    "Do not invent information and include supporting article IDs when possible."
)


class QuestionAnswerService:
    def __init__(self, ai_provider):
        self.ai_provider = ai_provider

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
        return {
            "success": True,
            "answer": result["answer"],
            "supporting_article_ids": result.get("supporting_article_ids", []),
            "automatic": True,
            "provider": self.ai_provider.name,
        }

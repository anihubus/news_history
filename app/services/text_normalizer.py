import re


_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
    "in", "is", "it", "of", "on", "or", "that", "the", "to", "was",
    "were", "with", "this", "these", "those", "their", "they", "will",
}


def normalize_text(text):
    if not text:
        return []

    words = re.findall(r"[a-z0-9]+", text.lower())
    return [word for word in words if len(word) > 2 and word not in _STOP_WORDS]

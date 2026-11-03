import re

_PATTERNS = [
    (re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b"), "[CPF]"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "[EMAIL]"),
    (re.compile(r"\(?\d{2}\)?\s?9?\d{4}-?\d{4}"), "[TELEFONE]"),
    (re.compile(r"\b(?:\d[ -]?){13,16}\b"), "[CARTAO]"),
]


def redact(text: str) -> str:
    for pattern, label in _PATTERNS:
        text = pattern.sub(label, text)
    return text

"""Provider-independent conservative token estimation."""

from __future__ import annotations

import math
import re
from collections.abc import Iterable

from stem_sci.compat.langchain import BaseMessage

_CJK = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]")


def estimate_text_tokens(text: str) -> int:
    """Estimate tokens conservatively without coupling to a provider tokenizer."""

    cjk_count = len(_CJK.findall(text))
    non_cjk_count = max(0, len(text) - cjk_count)
    return max(1, cjk_count + math.ceil(non_cjk_count / 3.2))


def estimate_message_tokens(messages: Iterable[BaseMessage]) -> int:
    total = 0
    for message in messages:
        content = message.content if isinstance(message.content, str) else str(message.content)
        total += 4 + estimate_text_tokens(content)
    return total + 2

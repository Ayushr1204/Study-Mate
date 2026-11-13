"""Token counting.

Uses tiktoken when its encoding is available. tiktoken downloads its vocabulary on
first use; in an air-gapped environment that fails, so we fall back to a clearly
labelled approximation (chars / 4). The active counter's name is included in every
context statistic so the UI never presents an estimate as exact.
"""

from __future__ import annotations

import math
from typing import Any

from langchain_core.messages import BaseMessage

PER_MESSAGE_OVERHEAD = 4  # role/formatting tokens, as in the OpenAI chat format


def content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
        return "\n".join(parts)
    return str(content)


class TokenCounter:
    def __init__(self, mode: str = "auto", encoding: str = "cl100k_base"):
        self._enc = None
        self.name = "approx:chars/4"
        if mode in ("auto", "tiktoken"):
            try:
                import tiktoken

                self._enc = tiktoken.get_encoding(encoding)
                self.name = f"tiktoken:{encoding}"
            except Exception as exc:  # network/cache failure
                if mode == "tiktoken":
                    raise RuntimeError(f"tiktoken encoding {encoding!r} unavailable: {exc}") from exc
        self.exact = self._enc is not None

    def count_text(self, text: str) -> int:
        if not text:
            return 0
        if self._enc is not None:
            return len(self._enc.encode(text, disallowed_special=()))
        return math.ceil(len(text) / 4)

    def count_message(self, message: BaseMessage) -> int:
        return self.count_text(content_to_text(message.content)) + PER_MESSAGE_OVERHEAD

    def count_messages(self, messages: list[BaseMessage]) -> int:
        return sum(self.count_message(m) for m in messages)

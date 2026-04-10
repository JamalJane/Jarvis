"""
ContextGuard — 3-stage context overflow protection for Jarvis.

Stage 1: Truncate oversized tool/screenshot content (head-only)
Stage 2: Compact the first 50% of messages into an LLM summary
Stage 3: Raise if still overflowing

Ported from reference implementation, adapted for Jarvis's Gemini API manager.
"""
import json
import logging
import math
from typing import Any, List, Dict, Optional

logger = logging.getLogger(__name__)

CONTEXT_SAFE_LIMIT = 180_000   # ~180k token estimate threshold
MAX_TOOL_OUTPUT    = 50_000    # max chars per tool / screenshot result


def _serialize_messages(messages: List[Dict]) -> str:
    """Flatten messages to plain text for LLM summarization."""
    parts: List[str] = []
    for msg in messages:
        role = msg.get("role", "?")
        content = msg.get("content", "")
        if isinstance(content, str):
            parts.append(f"[{role}]: {content}")
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    btype = block.get("type", "")
                    if btype == "text":
                        parts.append(f"[{role}]: {block['text']}")
                    elif btype == "tool_use":
                        parts.append(
                            f"[{role} called {block.get('name', '?')}]: "
                            f"{json.dumps(block.get('input', {}))}"
                        )
                    elif btype == "tool_result":
                        rc = block.get("content", "")
                        preview = rc[:500] if isinstance(rc, str) else str(rc)[:500]
                        parts.append(f"[tool_result]: {preview}")
    return "\n".join(parts)


class ContextGuard:
    """Protects Jarvis's conversation loop from context window overflow."""

    def __init__(self, max_tokens: int = CONTEXT_SAFE_LIMIT):
        self.max_tokens = max_tokens

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Rough estimate: 1 token = 4 characters."""
        return len(text) // 4

    def estimate_messages_tokens(self, messages: List[Dict]) -> int:
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total += self.estimate_tokens(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        if "text" in block:
                            total += self.estimate_tokens(block["text"])
                        elif block.get("type") == "tool_result":
                            rc = block.get("content", "")
                            if isinstance(rc, str):
                                total += self.estimate_tokens(rc)
                        elif block.get("type") == "tool_use":
                            total += self.estimate_tokens(json.dumps(block.get("input", {})))
        return total

    def truncate_result(self, result: str, max_fraction: float = 0.3) -> str:
        """Head-only truncation to max_fraction of context budget."""
        max_chars = int(self.max_tokens * 4 * max_fraction)
        if len(result) <= max_chars:
            return result
        head = result[:max_chars]
        return head + f"\n\n[... truncated ({len(result)} chars total)]"

    def compact_history(self, messages: List[Dict], api_manager) -> List[Dict]:
        """
        Compress the first 50% of messages into an LLM summary.
        Keeps the last 20% (min 4) for recent context continuity.
        """
        total = len(messages)
        if total <= 4:
            return messages

        keep_count    = max(4, int(total * 0.2))
        compress_count = max(2, min(int(total * 0.5), total - keep_count))

        if compress_count < 2:
            return messages

        old_messages    = messages[:compress_count]
        recent_messages = messages[compress_count:]
        old_text        = _serialize_messages(old_messages)

        summary_prompt = (
            "Summarize the following conversation concisely, "
            "preserving key facts and decisions. "
            "Output only the summary, no preamble.\n\n"
            f"{old_text}"
        )

        try:
            summary_text = api_manager.call_api(summary_prompt)
            logger.info(
                f"[context_guard] Compacted {len(old_messages)} messages → "
                f"summary ({len(summary_text)} chars)"
            )
        except Exception as exc:
            logger.warning(f"[context_guard] Compaction summary failed ({exc}), dropping old messages")
            return recent_messages

        compacted = [
            {
                "role": "user",
                "content": "[Previous conversation summary]\n" + summary_text,
            },
            {
                "role": "assistant",
                "content": "Understood, I have the context from our previous conversation.",
            },
        ]
        compacted.extend(recent_messages)
        return compacted

    def _truncate_large_content(self, messages: List[Dict]) -> List[Dict]:
        """Walk through messages, truncate oversized content blocks."""
        result = []
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, list):
                new_blocks = []
                for block in content:
                    if (isinstance(block, dict)
                            and block.get("type") == "tool_result"
                            and isinstance(block.get("content"), str)):
                        block = dict(block)
                        block["content"] = self.truncate_result(block["content"])
                    new_blocks.append(block)
                result.append({"role": msg["role"], "content": new_blocks})
            elif isinstance(content, str) and len(content) > self.max_tokens * 4 * 0.5:
                result.append({"role": msg["role"], "content": self.truncate_result(content, 0.5)})
            else:
                result.append(msg)
        return result

    def guard_call(
        self,
        api_manager,
        prompt: str,
        screenshot_b64: Optional[str],
        messages: List[Dict],
        max_retries: int = 2,
    ) -> str:
        """
        3-stage retry around an API call.
          Attempt 0: normal call
          Attempt 1: truncate large content in messages
          Attempt 2: compact history via LLM summary
        """
        current_messages = list(messages)

        for attempt in range(max_retries + 1):
            try:
                return api_manager.call_api(prompt, screenshot_b64)
            except Exception as exc:
                err = str(exc).lower()
                is_overflow = ("context" in err or "token" in err or "length" in err)

                if not is_overflow or attempt >= max_retries:
                    raise

                if attempt == 0:
                    logger.warning("[context_guard] Context overflow → truncating content...")
                    current_messages = self._truncate_large_content(current_messages)
                    messages.clear()
                    messages.extend(current_messages)
                elif attempt == 1:
                    logger.warning("[context_guard] Still overflowing → compacting history...")
                    current_messages = self.compact_history(current_messages, api_manager)
                    messages.clear()
                    messages.extend(current_messages)

        raise RuntimeError("ContextGuard: exhausted all retries")

    def usage_report(self, messages: List[Dict]) -> Dict[str, Any]:
        estimated = self.estimate_messages_tokens(messages)
        pct = (estimated / self.max_tokens) * 100
        return {
            "estimated_tokens": estimated,
            "limit": self.max_tokens,
            "percent": round(pct, 1),
            "status": "ok" if pct < 70 else ("warn" if pct < 90 else "critical"),
            "message_count": len(messages),
        }

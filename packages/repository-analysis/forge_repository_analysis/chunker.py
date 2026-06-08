from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

CHUNK_TOKENS = 512
OVERLAP_TOKENS = 64


class CodeChunker:
    def __init__(self, chunk_tokens: int = CHUNK_TOKENS, overlap_tokens: int = OVERLAP_TOKENS) -> None:
        self._chunk_tokens = chunk_tokens
        self._overlap_tokens = overlap_tokens
        self._enc = self._load_encoding()

    def _load_encoding(self):  # type: ignore[return]
        try:
            import tiktoken
            return tiktoken.get_encoding("cl100k_base")
        except Exception:
            logger.warning("tiktoken not available; falling back to character-based splitting")
            return None

    def chunk(self, content: str, file_path: str = "") -> list[dict[str, object]]:
        """Split content into overlapping token-windowed chunks."""
        lines = content.splitlines(keepends=True)
        if not lines:
            return []

        if self._enc is None:
            return self._chunk_by_chars(content)

        return self._chunk_by_tokens(lines)

    def _chunk_by_tokens(self, lines: list[str]) -> list[dict[str, object]]:
        chunks: list[dict[str, object]] = []
        current_tokens: list[int] = []
        current_lines: list[int] = []
        line_num = 1
        chunk_index = 0

        for line in lines:
            line_tokens = self._enc.encode(line)
            if (
                len(current_tokens) + len(line_tokens) > self._chunk_tokens
                and current_tokens
            ):
                content = self._enc.decode(current_tokens)
                chunks.append({
                    "chunk_index": chunk_index,
                    "content": content,
                    "start_line": current_lines[0] if current_lines else line_num,
                    "end_line": current_lines[-1] if current_lines else line_num,
                })
                chunk_index += 1
                # Keep overlap
                overlap_start = max(0, len(current_tokens) - self._overlap_tokens)
                current_tokens = current_tokens[overlap_start:]
                overlap_line_count = len(self._enc.decode(current_tokens).splitlines())
                current_lines = current_lines[-overlap_line_count:] if current_lines else []

            current_tokens.extend(line_tokens)
            current_lines.append(line_num)
            line_num += 1

        if current_tokens:
            chunks.append({
                "chunk_index": chunk_index,
                "content": self._enc.decode(current_tokens),
                "start_line": current_lines[0] if current_lines else 1,
                "end_line": current_lines[-1] if current_lines else 1,
            })

        return chunks

    def _chunk_by_chars(self, content: str) -> list[dict[str, object]]:
        # Fallback: ~2000 char chunks with ~250 char overlap (approx 512/64 tokens)
        size = 2000
        overlap = 250
        chunks = []
        start = 0
        chunk_index = 0
        while start < len(content):
            end = min(start + size, len(content))
            chunk_content = content[start:end]
            start_line = content[:start].count("\n") + 1
            end_line = content[:end].count("\n") + 1
            chunks.append({
                "chunk_index": chunk_index,
                "content": chunk_content,
                "start_line": start_line,
                "end_line": end_line,
            })
            chunk_index += 1
            start = end - overlap if end < len(content) else end
        return chunks

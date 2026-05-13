"""Token-aware diff chunker using tiktoken."""

from __future__ import annotations

import tiktoken


class DiffChunker:
    """Split diffs into token-bounded chunks respecting hunk boundaries."""

    def __init__(self) -> None:
        """Initialize chunker with tiktoken encoder."""
        self._encoder = tiktoken.get_encoding("cl100k_base")

    def _count_tokens(self, text: str) -> int:
        """Count tokens in a string using cl100k_base encoding."""
        return len(self._encoder.encode(text))

    def chunk(self, text: str, chunk_size: int = 1500, overlap: int = 200) -> list[str]:
        """Split text into token-bounded chunks respecting diff hunk boundaries.

        Args:
            text: The text to chunk
            chunk_size: Maximum tokens per chunk
            overlap: Number of tokens to overlap between chunks

        Returns:
            List of non-empty chunk strings
        """
        if not text:
            return []

        lines = text.split("\n")
        chunks = []
        current_chunk_lines = []
        current_tokens = 0

        for line in lines:
            line_tokens = self._count_tokens(line + "\n")

            # If adding this line would exceed chunk_size, finalize current chunk
            if current_tokens + line_tokens > chunk_size and current_chunk_lines:
                chunk_text = "\n".join(current_chunk_lines)
                chunks.append(chunk_text)

                # Calculate overlap for next chunk
                overlap_lines = []
                overlap_tokens = 0
                for overlap_line in reversed(current_chunk_lines):
                    overlap_line_tokens = self._count_tokens(overlap_line + "\n")
                    if overlap_tokens + overlap_line_tokens <= overlap:
                        overlap_lines.insert(0, overlap_line)
                        overlap_tokens += overlap_line_tokens
                    else:
                        break

                current_chunk_lines = overlap_lines
                current_tokens = overlap_tokens

            current_chunk_lines.append(line)
            current_tokens += line_tokens

        # Add final chunk
        if current_chunk_lines:
            chunks.append("\n".join(current_chunk_lines))

        return [c for c in chunks if c.strip()]

    def chunk_by_file(self, parsed_files: list[dict]) -> list[dict]:
        """Chunk each file's diff content individually and tag with metadata.

        Args:
            parsed_files: Output of GitDiffParser.parse_changed_files()

        Returns:
            List of dicts with file_path, chunk_index, total_chunks, content, token_count
        """
        result = []
        for file_info in parsed_files:
            file_path = file_info["file_path"]
            hunks = file_info.get("hunks", [])
            content = "\n".join(hunks)

            if not content.strip():
                continue

            chunks = self.chunk(content)
            total_chunks = len(chunks)

            for chunk_idx, chunk in enumerate(chunks):
                token_count = self._count_tokens(chunk)
                result.append(
                    {
                        "file_path": file_path,
                        "chunk_index": chunk_idx,
                        "total_chunks": total_chunks,
                        "content": chunk,
                        "token_count": token_count,
                    }
                )

        return result

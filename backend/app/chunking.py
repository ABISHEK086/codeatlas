from dataclasses import dataclass

MAX_LINES = 60


@dataclass
class ChunkSpan:
    start_line: int
    end_line: int
    content: str


def _windows(lines: list[str], start: int, end: int, size: int) -> list[ChunkSpan]:
    out = []
    for a in range(start, end + 1, size):
        b = min(a + size - 1, end)
        text = "\n".join(lines[a - 1:b])
        if text.strip():
            out.append(ChunkSpan(a, b, text))
    return out


def chunk_file(content: str, symbols: list[tuple[int, int]], size: int = MAX_LINES) -> list[ChunkSpan]:
    """symbols: [(start_line, end_line)]. Outermost symbols become one chunk each,
    gaps between them are windowed, oversized pieces are split."""
    lines = content.splitlines()
    n = len(lines)
    if n == 0:
        return []

    spans: list[tuple[int, int]] = []
    last_end = 0
    for start, end in sorted(symbols, key=lambda s: (s[0], -s[1])):
        if start <= last_end:          # nested (e.g. a method inside a class)
            continue
        end = min(end, n)
        spans.append((start, end))
        last_end = end

    segments: list[tuple[int, int]] = []
    cursor = 1
    for start, end in spans:
        if start > cursor:
            segments.append((cursor, start - 1))
        segments.append((start, end))
        cursor = end + 1
    if cursor <= n:
        segments.append((cursor, n))

    chunks: list[ChunkSpan] = []
    for a, b in segments:
        chunks.extend(_windows(lines, a, b, size))
    return chunks
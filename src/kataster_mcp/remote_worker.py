"""Disposable parser process; inputs and outputs are bounded by the HTTP parent."""

import io
import json
import sys


def main() -> None:
    if sys.platform == "linux":
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (512 * 1024**2, 512 * 1024**2))
        resource.setrlimit(resource.RLIMIT_CPU, (15, 15))
    from .lv import parse_page

    raw = sys.stdin.buffer.read(5 * 1024**2 + 1)
    if len(raw) > 5 * 1024**2:
        raise ValueError("Upload too large")
    if raw.startswith(b"%PDF"):
        from pypdf import PdfReader

        if len(PdfReader(io.BytesIO(raw)).pages) > 100:
            raise ValueError("PDF page limit exceeded")
    result = json.dumps(parse_page(raw), ensure_ascii=True).encode()
    if len(result) > 2 * 1024**2:
        raise ValueError("Parsed document too large")
    sys.stdout.buffer.write(result)


if __name__ == "__main__":
    main()

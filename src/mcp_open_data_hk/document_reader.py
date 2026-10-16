"""Isolated PDF extraction worker. Called with CPU, address-space and output limits."""

import io
import json
import sys

from pypdf import PdfReader


def main():
    from .resource_formats import document_limits

    document_limits()
    body = sys.stdin.buffer.read(8_000_001)
    if len(body) > 8_000_000:
        raise ValueError("Document byte limit")
    reader = PdfReader(io.BytesIO(body), strict=True)
    if reader.is_encrypted or len(reader.pages) > 200:
        raise ValueError("Encrypted or oversized document")
    rows = [
        {"page": i + 1, "text": page.extract_text() or ""}
        for i, page in enumerate(reader.pages)
    ]
    json.dump(rows, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()

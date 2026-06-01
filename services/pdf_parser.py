"""
services/pdf_parser.py — In-memory PDF text extraction via PyMuPDF.
"""

import fitz  # PyMuPDF


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """
    Parse PDF bytes in-memory and return the concatenated text of all pages.

    Args:
        file_bytes: Raw PDF file content.

    Returns:
        Extracted text, or a placeholder if the PDF contains no readable text.

    Raises:
        Exception: Any error from PyMuPDF during parsing.
    """
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    extracted = "\n".join(doc.load_page(i).get_text() for i in range(len(doc)))

    if not extracted.strip():
        return "[No readable text found in this PDF]"

    return extracted

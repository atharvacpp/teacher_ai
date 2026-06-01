"""
services/llava_vision.py — Local LLaVA vision extraction via Ollama.

Handles visual text extraction using the locally-hosted LLaVA model
through the Ollama API at http://localhost:11434.

Two public coroutines:
  • extract_text_from_image  — single image → LLaVA → extracted text
  • extract_text_from_pdf_vision — PDF → per-page PNG slicing → LLaVA loop
"""

import base64

import fitz  # PyMuPDF
import httpx

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

OLLAMA_URL = "http://localhost:11434/api/chat"
LLAVA_MODEL = "llava"

VISION_PROMPT = (
    "Extract and transcribe all text, formulas, "
    "and visual data from this image."
)


# ---------------------------------------------------------------------------
# Single-Image Extraction
# ---------------------------------------------------------------------------

async def extract_text_from_image(image_bytes: bytes) -> str:
    """
    Send a single image to the local LLaVA model via Ollama and
    extract all readable text, formulas, and visual data.

    Args:
        image_bytes: Raw bytes of the image file (PNG, JPEG, etc.).

    Returns:
        The extracted text string from LLaVA.

    Raises:
        httpx.ConnectError: If Ollama is not running at localhost:11434.
        httpx.HTTPStatusError: If the Ollama API returns a non-200 status.
    """
    b64_image = base64.b64encode(image_bytes).decode("utf-8")

    payload = {
        "model": LLAVA_MODEL,
        "messages": [
            {
                "role": "user",
                "content": VISION_PROMPT,
                "images": [b64_image],
            }
        ],
        "stream": False,
    }

    async with httpx.AsyncClient(timeout=180.0) as client:
        response = await client.post(OLLAMA_URL, json=payload)
        response.raise_for_status()
        data = response.json()

    extracted = data.get("message", {}).get("content", "")
    print(f"[LLaVA] Extracted {len(extracted)} characters from image.")
    return extracted


# ---------------------------------------------------------------------------
# PDF Vision Loop (Handwritten / Scanned Documents)
# ---------------------------------------------------------------------------

async def extract_text_from_pdf_vision(file_bytes: bytes) -> str:
    """
    Slice a PDF into per-page PNG images and extract text from each
    page using LLaVA via the local Ollama instance.

    Designed for handwritten or scanned PDFs where standard digital
    text extraction (PyMuPDF) yields little or no content.

    Each page is rendered at 200 DPI, converted to PNG in-memory,
    and sent to LLaVA. Memory is freed immediately after each page
    to keep the footprint manageable for large documents.

    Args:
        file_bytes: Raw bytes of the PDF file.

    Returns:
        Concatenated extracted text from all pages, separated by
        ``--- Page N ---`` headers.
    """
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    page_count = len(doc)
    print(
        f"[LLaVA] Slicing PDF into {page_count} page image(s) "
        f"for vision extraction..."
    )

    all_text: list[str] = []

    for i in range(page_count):
        page = doc.load_page(i)

        # Render page → PNG at 200 DPI (balance of quality vs memory)
        pixmap = page.get_pixmap(dpi=200)
        png_bytes = pixmap.tobytes("png")

        print(
            f"[LLaVA] Processing page {i + 1}/{page_count} "
            f"({len(png_bytes):,} bytes)..."
        )

        page_text = await extract_text_from_image(png_bytes)
        all_text.append(f"--- Page {i + 1} ---\n{page_text}")

        # Explicitly free heavy objects to limit memory pressure
        del pixmap, png_bytes

    doc.close()

    full_text = "\n\n".join(all_text)
    print(
        f"[LLaVA] PDF vision extraction complete. "
        f"Total: {len(full_text):,} characters across {page_count} page(s)."
    )
    return full_text

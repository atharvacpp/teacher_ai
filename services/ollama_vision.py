"""
services/ollama_vision.py — Remote Ollama qwen3-vl extraction pipeline.

Handles visual extraction via remote Ollama Cloud instance.
Supports async streaming to cleanly abort generation if the client disconnects.
The extracted text is then passed to the Hugging Face text pipeline.
"""

import base64
import json
import httpx
from fastapi import Request, HTTPException
import fitz  # PyMuPDF

from config import OLLAMA_BASE_URL, OLLAMA_API_KEY, OLLAMA_VLM_MODEL


async def extract_text_from_image(
    request: Request,
    file_bytes: bytes,
    content_type: str,
    user_prompt: str | None = None,
) -> str:
    """
    Sends visual data directly to a remote Ollama qwen3-vl instance to
    extract text. Uses async streaming and aborts early if the FastAPI request 
    disconnects (e.g. user hits stop).

    Args:
        request: The FastAPI Request object (to check disconnected state).
        file_bytes: Raw bytes of the uploaded file.
        content_type: MIME type (e.g. image/png, application/pdf).
        user_prompt: Optional user context.

    Returns:
        The extracted literal text description.
    """
    print("=" * 60)
    print(f"[Ollama Vision] Starting async extraction...")
    print(f"  content_type : {content_type}")
    print("=" * 60)

    # 1. Prepare Base64 Images
    b64_images: list[str] = []

    if content_type == "application/pdf":
        print("[Ollama Vision] Rendering PDF pages to images...")
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        for i in range(len(doc)):
            page = doc.load_page(i)
            pixmap = page.get_pixmap(dpi=300)
            png_bytes = pixmap.tobytes("png")
            b64_images.append(base64.b64encode(png_bytes).decode("utf-8"))
        doc.close()
    elif content_type.startswith("image/") or content_type.startswith("video/"):
        b64_images.append(base64.b64encode(file_bytes).decode("utf-8"))
    else:
        raise ValueError(f"Unsupported visual content type: {content_type}")

    # 2. Prepare Prompt
    prompt = (
        "Extract all readable text, formulas, or handwriting from this image, "
        "and provide a literal description of any diagrams."
    )

    # 3. Prepare Payload
    payload = {
        "model": OLLAMA_VLM_MODEL,
        "messages": [
            {
                "role": "user",
                "content": prompt,
                "images": b64_images,
            }
        ],
        "stream": True,
        "options": {
            "num_ctx": 4096,
            "temperature": 0.1,
        }
    }

    headers = {}
    if OLLAMA_API_KEY:
        headers["Authorization"] = f"Bearer {OLLAMA_API_KEY}"

    ollama_url = f"{OLLAMA_BASE_URL.rstrip('/')}/api/chat"

    print(f"[Ollama Vision] Connecting to {ollama_url} (stream=True)")

    # 4. Async Stream & Disconnect Check
    collected_text = []

    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            async with client.stream(
                "POST", ollama_url, json=payload, headers=headers
            ) as response:
                
                if response.status_code != 200:
                    await response.aread()
                    error_msg = response.text[:300]
                    raise HTTPException(
                        status_code=503,
                        detail=f"Ollama API returned HTTP {response.status_code}: {error_msg}"
                    )

                async for line in response.aiter_lines():
                    if not line:
                        continue

                    # Check client disconnection
                    if await request.is_disconnected():
                        print("[Ollama Vision] Client disconnected — aborting stream.")
                        # Raise an exception so we don't accidentally pass partial
                        # text to the HF text models.
                        raise HTTPException(status_code=499, detail="Client Closed Request")

                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    token = chunk.get("message", {}).get("content", "")
                    if token:
                        collected_text.append(token)

                    if chunk.get("done", False):
                        break

    except httpx.RequestError as e:
        print(f"[Ollama Vision] Request failed: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"Failed to connect to remote Ollama vision engine: {e}"
        )

    final_text = "".join(collected_text)
    
    if not final_text.strip():
        raise HTTPException(
            status_code=503,
            detail="Ollama vision model returned an empty response."
        )

    print(f"[Ollama Vision] Extracted {len(final_text)} characters.")
    return final_text

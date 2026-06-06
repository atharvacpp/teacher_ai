"""
routers/pipeline_a_reasoning.py — POST /upload endpoint (Phase 5: Pipeline A).

Implements a dynamic routing system for uploaded files:

  LANE 1 — Fast Digital (PyMuPDF)
    • Trigger:  PDF + force_vision=False  (default)
    • Method:   fitz in-memory text extraction — no model calls

  LANE 2 — Heavy Vision (LLaVA via Ollama)
    • Trigger:  PDF + force_vision=True
    • Method:   Slice PDF into per-page PNGs → LLaVA vision loop

  LANE 3 — Direct Image (LLaVA via Ollama)
    • Trigger:  image/* MIME type
    • Method:   Raw image bytes → Base64 → LLaVA single-shot

After extraction, the text is routed through Pipeline A:
  Teacher -> Reviewer -> END

The response is returned as JSON matching the ChatResponse schema.
"""

from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import StreamingResponse

from services.pdf_parser import extract_text_from_pdf
from services.llava_vision import (
    extract_text_from_image,
    extract_text_from_pdf_vision,
)
from services.pipeline_a_reasoning import stream_pipeline_a

router = APIRouter(tags=["Upload / Pipeline A"])


@router.post("/upload")
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    prompt: str | None = Form(None),
    force_vision: bool = Form(False),
):
    # ------------------------------------------------------------------
    # 0. Read and validate the upload
    # ------------------------------------------------------------------
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    content_type = file.content_type or ""
    user_prompt = prompt.strip() if prompt and prompt.strip() else None

    print("=" * 60)
    print(f"[Pipeline A] New file received")
    print(f"  filename      : {file.filename}")
    print(f"  content_type  : {content_type}")
    print(f"  force_vision  : {force_vision}")
    print("=" * 60)

    # ------------------------------------------------------------------
    # 1. Text Extraction — route to the correct pipeline
    # ------------------------------------------------------------------
    extracted_text = ""

    try:
        if content_type == "application/pdf":
            if force_vision:
                print("[Pipeline A] Handwritten PDF → routing to LLaVA vision loop")
                extracted_text = await extract_text_from_pdf_vision(file_bytes)
            else:
                print("[Pipeline A] Digital PDF → routing to PyMuPDF fast extraction")
                extracted_text = extract_text_from_pdf(file_bytes)

        elif content_type.startswith("image/"):
            print("[Pipeline A] Image upload → routing to LLaVA")
            extracted_text = await extract_text_from_image(file_bytes)

        else:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Unsupported file type: {content_type}. "
                    "Please upload a PDF or image (PNG, JPEG, etc.)."
                ),
            )

    except HTTPException:
        raise
    except Exception as exc:
        print(f"[Pipeline A] Extraction error: {exc}")
        raise HTTPException(
            status_code=500,
            detail=f"Text extraction failed: {exc}",
        ) from exc

    if not extracted_text or not extracted_text.strip():
        raise HTTPException(
            status_code=422,
            detail=(
                "No readable content could be extracted from the uploaded file. "
                "If this is a scanned or handwritten PDF, try re-uploading with "
                "the handwriting toggle enabled."
            ),
        )

    print(f"[Pipeline A] Extraction complete. Handing off to reasoning graph...")

    # ------------------------------------------------------------------
    # 2. Stream Pipeline A Reasoning Graph
    # ------------------------------------------------------------------
    async def event_stream():
        try:
            async for chunk in stream_pipeline_a(
                extracted_text=extracted_text,
                user_prompt=user_prompt,
            ):
                if await request.is_disconnected():
                    break
                yield chunk
        except Exception as exc:
            import json
            print(f"[Pipeline A] Orchestrator error: {exc}")
            yield "data: " + json.dumps({"type": "error", "content": f"Lesson generation failed: {exc}"}) + "\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")

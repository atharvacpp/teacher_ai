"""
routers/upload.py — POST /upload endpoint.

Implements the Hybrid Two-Step Handoff Architecture:

  • Images →
      Step 1: Ollama LLaVA extracts text/formulas/diagrams locally (free)
      Step 2: HuggingFace Qwen2.5 generates the final explanation (cloud)

  • PDFs →
      Step 1: PyMuPDF extracts text in-memory
      Step 2: HuggingFace Qwen2.5 generates the final explanation
"""

import base64

import requests
from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Form

from schemas import ChatResponse
from services.hf_chat import generate_chat_response
from services.ollama_vision import analyze_image
from services.pdf_parser import extract_text_from_pdf
from services.tts import generate_tts_audio

router = APIRouter(tags=["Upload"])

# The fixed extraction prompt sent to Ollama LLaVA (Step 1).
# This is intentionally hardcoded — LLaVA's job is *only* to extract raw
# visual content.  The creative reasoning happens in Step 2 (Qwen).
VISION_EXTRACTION_PROMPT = (
    "Extract all readable text, formulas, or handwriting from this image, "
    "and provide a literal description of any diagrams."
)


@router.post("/upload", response_model=ChatResponse)
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    prompt: str | None = Form(None),
    force_vision: bool = Form(False),
):
    """
    Accepts an uploaded image or PDF file and an optional user prompt.

    Images use the **Two-Step Handoff**:
      1. Ollama LLaVA (local) extracts visual content from the image.
      2. HuggingFace Qwen2.5 (cloud) generates the final explanation
         using the extraction + the user's prompt.

    PDFs have two modes controlled by the *force_vision* flag:
      • **force_vision=False** (default): PyMuPDF extracts digital text,
        then Qwen2.5 generates an explanation.
      • **force_vision=True**: Each page is rendered as an image and
        routed through the Two-Step Vision Pipeline (LLaVA → Qwen) so
        that handwritten notes, diagrams, and scanned content can be
        read.
    """
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    content_type = file.content_type or ""

    # Clean the prompt
    user_prompt = prompt.strip() if prompt and prompt.strip() else None

    # ------------------------------------------------------------------
    # 1. Handle Images — Two-Step Handoff (Ollama → Qwen)
    # ------------------------------------------------------------------
    if content_type.startswith("image/"):
        b64_img = base64.b64encode(file_bytes).decode("utf-8")

        # ── Step 1: Vision Extraction via Local Ollama/LLaVA ──────────
        try:
            extracted_visual_context = analyze_image(
                b64_image=b64_img,
                prompt=VISION_EXTRACTION_PROMPT,
                disconnect_check=lambda: request.is_disconnected(),
            )
        except requests.exceptions.ConnectionError as conn_exc:
            from config import OLLAMA_BASE_URL
            print(f"[upload] Cannot connect to Ollama at {OLLAMA_BASE_URL}: {conn_exc}")
            raise HTTPException(
                status_code=503,
                detail=(
                    f"Cannot connect to Ollama at {OLLAMA_BASE_URL}. "
                    "Please make sure Ollama is running ('ollama serve')."
                ),
            ) from conn_exc

        except requests.exceptions.Timeout as timeout_exc:
            raise HTTPException(
                status_code=504,
                detail="Ollama took too long to respond. The model may still be loading — please try again.",
            ) from timeout_exc

        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Vision extraction error (Ollama): {repr(exc)}",
            ) from exc

        # Abort early if the client disconnected during Step 1
        if await request.is_disconnected():
            return ChatResponse(explanation="⏹ Generation stopped.", audio_base64=None)

        print("====== STEP 1 COMPLETE: VISUAL EXTRACTION ======")
        print(f"Extracted context ({len(extracted_visual_context)} chars):")
        print(extracted_visual_context[:300])
        print("=================================================")

        # ── Step 2: Final Explanation via HuggingFace Qwen ────────────
        if user_prompt:
            combined_prompt = (
                f"{user_prompt}\n\n"
                f"--- Visual Context (extracted from the uploaded image) ---\n"
                f"{extracted_visual_context}"
            )
        else:
            combined_prompt = (
                f"Based on the following content extracted from an uploaded image, "
                f"provide a clear, detailed explanation:\n\n"
                f"--- Visual Context ---\n"
                f"{extracted_visual_context}"
            )

        try:
            explanation = generate_chat_response(
                [{"role": "user", "content": combined_prompt}]
            )
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail=f"LLM explanation error (Qwen): {exc}",
            ) from exc

    # ------------------------------------------------------------------
    # 2. Handle PDFs
    # ------------------------------------------------------------------
    elif content_type == "application/pdf":

        # ── 2a. Vision Mode — render pages as images, route via LLaVA ─
        if force_vision:
            import fitz  # PyMuPDF

            print("====== PDF VISION MODE (force_vision=True) ======")
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            page_extractions: list[str] = []

            for page_num, page in enumerate(doc, start=1):
                if await request.is_disconnected():
                    return ChatResponse(
                        explanation="⏹ Generation stopped.", audio_base64=None
                    )

                # Render the page at 300 DPI for high-quality OCR
                pixmap = page.get_pixmap(dpi=300)
                png_bytes = pixmap.tobytes("png")
                b64_page = base64.b64encode(png_bytes).decode("utf-8")

                print(f"  → Page {page_num}/{len(doc)}: "
                      f"{pixmap.width}×{pixmap.height}px, "
                      f"{len(b64_page)} chars (base64)")

                # Step 1: LLaVA extracts text / handwriting from the page
                try:
                    page_text = analyze_image(
                        b64_image=b64_page,
                        prompt=VISION_EXTRACTION_PROMPT,
                        disconnect_check=lambda: request.is_disconnected(),
                    )
                except requests.exceptions.ConnectionError as conn_exc:
                    from config import OLLAMA_BASE_URL
                    raise HTTPException(
                        status_code=503,
                        detail=(
                            f"Cannot connect to Ollama at {OLLAMA_BASE_URL}. "
                            "Please make sure Ollama is running ('ollama serve')."
                        ),
                    ) from conn_exc
                except requests.exceptions.Timeout as timeout_exc:
                    raise HTTPException(
                        status_code=504,
                        detail=(
                            f"Ollama timed out while processing page {page_num}. "
                            "The model may still be loading — please try again."
                        ),
                    ) from timeout_exc
                except Exception as exc:
                    raise HTTPException(
                        status_code=502,
                        detail=f"Vision extraction error on page {page_num}: {repr(exc)}",
                    ) from exc

                page_extractions.append(
                    f"--- Page {page_num} ---\n{page_text}"
                )

            doc.close()
            extracted_visual_context = "\n\n".join(page_extractions)

            print("====== PDF VISION EXTRACTION COMPLETE ======")
            print(f"Total extracted ({len(extracted_visual_context)} chars):")
            print(extracted_visual_context[:500])
            print("=============================================")

            # Step 2: Final Explanation via HuggingFace Qwen
            if user_prompt:
                combined_prompt = (
                    f"{user_prompt}\n\n"
                    f"--- Visual Context (extracted from PDF pages via vision) ---\n"
                    f"{extracted_visual_context}"
                )
            else:
                combined_prompt = (
                    "Based on the following content extracted from a PDF "
                    "(including any handwriting, diagrams, or formulas), "
                    "provide a clear, detailed explanation:\n\n"
                    f"--- Visual Context ---\n"
                    f"{extracted_visual_context}"
                )

            try:
                explanation = generate_chat_response(
                    [{"role": "user", "content": combined_prompt}]
                )
            except Exception as exc:
                raise HTTPException(
                    status_code=502,
                    detail=f"LLM explanation error (Qwen): {exc}",
                ) from exc

        # ── 2b. Standard Mode — PyMuPDF digital-text extraction ───────
        else:
            try:
                extracted_text = extract_text_from_pdf(file_bytes)
            except Exception as parse_exc:
                raise HTTPException(
                    status_code=500,
                    detail=f"PDF parsing failed: {parse_exc}",
                )

            if user_prompt:
                final_prompt = f"{user_prompt}\n\nDocument Context:\n{extracted_text}"
            else:
                final_prompt = f"Summarize and explain the following document:\n\n{extracted_text}"

            try:
                explanation = generate_chat_response(
                    [{"role": "user", "content": final_prompt}]
                )
            except Exception as exc:
                raise HTTPException(
                    status_code=502,
                    detail=f"LLM API error: {exc}",
                )

    # ------------------------------------------------------------------
    # 3. Unsupported Types
    # ------------------------------------------------------------------
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {content_type}. Please upload an image or PDF.",
        )

    # ------------------------------------------------------------------
    # 4. Generate TTS (skip if client disconnected)
    # ------------------------------------------------------------------
    audio_base64 = None
    if not await request.is_disconnected():
        audio_base64 = generate_tts_audio(explanation)

    return ChatResponse(
        explanation=explanation,
        audio_base64=audio_base64,
    )

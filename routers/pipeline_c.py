from fastapi import APIRouter, Request, HTTPException, UploadFile, File
from pydantic import BaseModel
from fastapi.responses import StreamingResponse

from services.pipeline_c_orchestrator import stream_pipeline_c

router = APIRouter(tags=["Pipeline C"])


class GenerateLessonRequest(BaseModel):
    topic: str


@router.post("/generate-lesson")
async def generate_lesson(
    request: Request,
    payload: GenerateLessonRequest,
):
    topic = payload.topic.strip()
    if not topic:
        raise HTTPException(status_code=400, detail="Topic is required.")

    print("=" * 60)
    print(f"[Pipeline C] New lesson generation requested")
    print(f"  topic      : {topic}")
    print("=" * 60)

    async def event_stream():
        try:
            async for chunk in stream_pipeline_c(topic=topic):
                if await request.is_disconnected():
                    break
                yield chunk
        except Exception as exc:
            import json
            print(f"[Pipeline C] Orchestrator error: {exc}")
            yield "data: " + json.dumps({"type": "error", "content": f"Lesson generation failed: {exc}"}) + "\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/api/ingest_memory")
async def ingest_memory(
    file: UploadFile = File(...),
):
    """
    Accepts an uploaded file (PDF or text), extracts its text,
    chunks it, embeds it via Ollama, and stores it in Pinecone
    for retrieval by the Self-RAG pipeline.
    """
    from services.pdf_parser import extract_text_from_pdf
    from services.rag_ingestion import process_and_store_document

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    content_type = file.content_type or ""
    filename = file.filename or "unknown_file"

    print(f"[Ingest Memory] Received file: {filename} ({content_type})")

    # Extract text based on file type
    extracted_text = ""
    try:
        if content_type == "application/pdf":
            extracted_text = extract_text_from_pdf(file_bytes)
        elif content_type.startswith("text/"):
            extracted_text = file_bytes.decode("utf-8", errors="ignore")
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {content_type}. Please upload a PDF or text file.",
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Text extraction failed: {exc}") from exc

    if not extracted_text or not extracted_text.strip():
        raise HTTPException(status_code=422, detail="No readable content found in the file.")

    # Ingest into Pinecone
    try:
        result = process_and_store_document(extracted_text, filename)
        return {
            "status": "success",
            "message": f"Document memorized! {result['chunks_created']} chunks stored.",
            "source": filename,
            "chunks_created": result["chunks_created"],
        }
    except Exception as exc:
        print(f"[Ingest Memory] Ingestion failed: {exc}")
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {exc}") from exc


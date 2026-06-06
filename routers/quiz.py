"""
routers/quiz.py — POST /api/generate-quiz endpoint (Focus Mode).

Accepts a video transcript and uses Qwen 2.5 via HuggingFace Inference API
to generate a structured multiple-choice quiz with strict JSON enforcement.

The quiz uses `correct_answer` (full text string) and `explanation_if_wrong`
so the frontend can grade answers client-side and display explanations only
for incorrect responses.
"""

import json
import re

from fastapi import APIRouter, HTTPException
from schemas import (
    GenerateQuizRequest,
    GenerateQuizResponse,
    QuizSchema,
)
from services.hf_chat import generate_chat_response

router = APIRouter(tags=["Quiz"])


# ---------------------------------------------------------------------------
# JSON extraction helper
# ---------------------------------------------------------------------------

def _extract_json(text: str) -> dict:
    """
    Try to extract a JSON object from model output.
    Handles markdown fenced blocks, raw JSON, and truncated JSON.
    """
    # Try fenced ```json ... ``` block first
    match = re.search(r"```json\s*\n(.*?)\n\s*```", text, re.DOTALL)
    if match:
        return json.loads(match.group(1))

    # Try fenced ``` ... ``` block (no language tag)
    match = re.search(r"```\s*\n(.*?)\n\s*```", text, re.DOTALL)
    if match:
        return json.loads(match.group(1))

    # Try raw JSON object
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return json.loads(match.group(0))

    # Try to repair truncated JSON (close open brackets/braces)
    match = re.search(r"\{.*", text, re.DOTALL)
    if match:
        partial = match.group(0)
        repaired = _repair_truncated_json(partial)
        if repaired:
            return repaired

    raise ValueError("No valid JSON found in model output.")


def _repair_truncated_json(text: str) -> dict | None:
    """
    Attempt to repair truncated JSON by closing unclosed brackets.
    Returns parsed dict or None if repair fails.
    """
    # Find the last complete question block
    # Strategy: remove everything after the last complete question object,
    # then close the arrays and root object.
    try:
        # Find all complete question objects ending with }
        # Look for the last `"explanation_if_wrong"` field that has a complete value
        last_complete = text.rfind('"explanation_if_wrong"')
        if last_complete == -1:
            return None

        # Find the closing brace of that question object
        pos = text.find('}', last_complete)
        if pos == -1:
            # Try to close the string and object
            text = text.rstrip()
            if not text.endswith('"'):
                text += '"'
            text += '}]}'
        else:
            # Check if there's a ] and } after
            remaining = text[pos+1:].strip()
            if remaining.startswith(','):
                # Truncated after a complete question — close the array
                text = text[:pos+1] + ']}'
            elif not remaining:
                text = text[:pos+1] + ']}'
            else:
                # Try the full remaining
                text = text[:pos+1] + ']}'

        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# POST /api/generate-quiz
# ---------------------------------------------------------------------------

@router.post("/api/generate-quiz", response_model=GenerateQuizResponse)
async def generate_quiz(payload: GenerateQuizRequest):
    """
    Generate a Focus Mode multiple-choice quiz from a video transcript.
    Uses Qwen 2.5 via HuggingFace with strict JSON schema enforcement.

    The returned schema uses `correct_answer` (the full option string) and
    `explanation_if_wrong` so the React UI can grade everything client-side
    and only reveal explanations for wrong answers.
    """
    transcript = payload.video_transcript.strip()
    if not transcript:
        raise HTTPException(
            status_code=400,
            detail="Video transcript is empty."
        )

    # Truncate very long transcripts to stay within token limits
    max_chars = 6000
    if len(transcript) > max_chars:
        transcript = transcript[:max_chars] + "..."

    print(f"[Quiz] Generating Focus Mode quiz for: {payload.video_title}")
    print(f"[Quiz] Transcript length: {len(transcript)} chars")

    system_prompt = """You are a quiz generation engine for an educational platform.
You MUST respond with ONLY a valid JSON object matching the exact schema below. No extra text, no markdown, no explanations outside the JSON.

JSON Schema:
{
  "quiz_title": "string — a short, engaging title for the quiz",
  "questions": [
    {
      "question_text": "string — the question",
      "options": ["option A", "option B", "option C", "option D"],
      "correct_answer": "option B",
      "explanation_if_wrong": "string — brief 1-2 sentence explanation"
    }
  ]
}

Critical Rules:
- Generate EXACTLY 5 questions.
- Each question MUST have EXACTLY 4 options.
- correct_answer MUST be the EXACT text of one of the 4 options (character-for-character match).
- ALL questions must be answerable ONLY from the provided transcript text. Do NOT use external knowledge.
- Keep ALL text SHORT: options under 60 chars, explanations under 150 chars.
- Do NOT prefix options with letters like "A)" or "B)" — just the answer text.
- Vary the difficulty: include 2 easy, 2 medium, and 1 hard question.
- Return ONLY the JSON object. Nothing else."""

    import random
    import time
    seed = f"{time.time()}-{random.randint(1000, 9999)}"

    user_prompt = f"""Generate a Focus Mode quiz based on this video transcript.

Video Title: {payload.video_title}

--- TRANSCRIPT ---
{transcript}
--- END TRANSCRIPT ---

To ensure variety, please select a DIFFERENT set of concepts to test than you normally would (Random Seed: {seed}).
Return ONLY the JSON object. No other text."""

    try:
        raw_response = generate_chat_response(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=4096,
            temperature=0.9,
        )
    except Exception as exc:
        print(f"[Quiz] HuggingFace API error: {exc}")
        raise HTTPException(
            status_code=502,
            detail=f"Quiz generation failed: {exc}",
        ) from exc

    print(f"[Quiz] Raw response length: {len(raw_response)} chars")
    print(f"[Quiz] Preview: {raw_response[:300]}")

    # Parse and validate the JSON response
    try:
        quiz_data = _extract_json(raw_response)
        quiz = QuizSchema(**quiz_data)
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"[Quiz] JSON parse error: {exc}")
        print(f"[Quiz] Raw output was: {raw_response[:500]}")
        raise HTTPException(
            status_code=502,
            detail=(
                "The AI returned an invalid quiz format. "
                "Please try again."
            ),
        ) from exc
    except Exception as exc:
        print(f"[Quiz] Validation error: {exc}")
        raise HTTPException(
            status_code=502,
            detail=f"Quiz validation failed: {exc}",
        ) from exc

    # Enforce structural guarantees
    for i, q in enumerate(quiz.questions):
        if len(q.options) != 4:
            raise HTTPException(
                status_code=502,
                detail=f"Question {i + 1} has {len(q.options)} options instead of 4."
            )
        if q.correct_answer not in q.options:
            # Attempt fuzzy match (strip whitespace)
            matched = False
            for opt in q.options:
                if opt.strip().lower() == q.correct_answer.strip().lower():
                    q.correct_answer = opt  # Fix to exact text
                    matched = True
                    break
            if not matched:
                raise HTTPException(
                    status_code=502,
                    detail=(
                        f"Question {i + 1}: correct_answer "
                        f"'{q.correct_answer}' does not match any option."
                    )
                )

    print(f"[Quiz] Successfully generated {len(quiz.questions)} questions.")
    return GenerateQuizResponse(quiz=quiz)

/**
 * api.js — API service layer for ExplainAI frontend.
 *
 * Handles all HTTP communication with the FastAPI backend.
 * Centralised here so every component can import a single, clean function
 * instead of scattering fetch logic throughout the UI code.
 */

// Base URL of the FastAPI backend (runs locally on port 8000)
const API_BASE_URL = "http://127.0.0.1:8000";

// ---------------------------------------------------------------------------
// POST /chat — send conversation history, get AI explanation
// ---------------------------------------------------------------------------

/**
 * Send the full conversation history to the /chat endpoint and return the
 * AI's explanation.
 *
 * @param {Array<{role: string, content: string}>} chatHistory - The full
 *   conversation so far (user + assistant messages).
 * @returns {Promise<string>} - The AI-generated explanation text.
 * @throws {Error} - Re-throws with a user-friendly message on failure.
 */
export async function sendChatMessage(chatHistory) {
  try {
    const response = await fetch(`${API_BASE_URL}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages: chatHistory }),
    });

    // If the backend returned an error status, surface the detail message
    if (!response.ok) {
      const errorData = await response.json().catch(() => null);
      throw new Error(
        errorData?.detail || `Server error (${response.status})`
      );
    }

    const data = await response.json();

    // Return the full object which now includes { explanation, audio_url }
    return data;
  } catch (error) {
    // Network failures, JSON parse errors, etc.
    console.error("[api] sendChatMessage failed:", error);
    throw error;
  }
}

// ---------------------------------------------------------------------------
// POST /transcribe — upload audio, get transcription text
// ---------------------------------------------------------------------------

/**
 * Upload a recorded audio Blob to the /transcribe endpoint and return the
 * transcribed text.
 *
 * @param {Blob} audioBlob - The recorded audio data (e.g. webm/opus).
 * @returns {Promise<string>} - The transcribed text from Distil-Whisper.
 * @throws {Error} - Re-throws with a user-friendly message on failure.
 */
export async function transcribeAudio(audioBlob) {
  // Abort the request if it takes longer than 120 seconds — prevents
  // infinite hangs when the HF model is cold-starting.
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 120_000);

  try {
    const formData = new FormData();
    // The key "file" must match the FastAPI parameter name
    formData.append("file", audioBlob, "recording.webm");

    const response = await fetch(`${API_BASE_URL}/transcribe`, {
      method: "POST",
      // Do NOT set Content-Type — the browser generates the correct
      // multipart/form-data boundary automatically.
      body: formData,
      signal: controller.signal,
    });

    if (!response.ok) {
      // Read the body as raw text first — response.json() was silently
      // failing and swallowing the actual error message from FastAPI.
      const rawText = await response.text().catch(() => "");
      let errorMessage = `Transcription error (${response.status})`;

      try {
        // FastAPI's HTTPException returns {"detail": "..."}
        const errorData = JSON.parse(rawText);
        errorMessage = errorData?.detail || errorData?.error || errorMessage;
      } catch {
        // Response wasn't valid JSON — use the raw text if available
        if (rawText) {
          errorMessage = rawText;
        }
      }

      throw new Error(errorMessage);
    }

    const data = await response.json();
    return data.transcription;
  } catch (error) {
    // Provide a clearer message for abort (timeout) errors
    if (error.name === "AbortError") {
      throw new Error(
        "Transcription request timed out. The model may be loading — please try again in 30 seconds."
      );
    }

    // Network-level failure (backend unreachable, CORS blocked, etc.)
    // fetch() throws a TypeError with a vague "Failed to fetch" message.
    if (error instanceof TypeError) {
      console.error("[api] transcribeAudio network error:", error);
      throw new Error(
        "Could not reach the backend server. Please check that uvicorn is running on port 8000."
      );
    }

    // HTTP errors (4xx/5xx) already have the specific FastAPI detail message
    // attached via the !response.ok branch above — just re-throw as-is.
    console.error("[api] transcribeAudio failed:", error);
    throw error;
  } finally {
    clearTimeout(timeoutId);
  }
}

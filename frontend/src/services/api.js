/**
 * api.js — API service layer for ExplainAI frontend.
 *
 * Handles all HTTP communication with the FastAPI backend.
 * Centralised here so every component can import a single, clean function
 * instead of scattering fetch logic throughout the UI code.
 *
 * Supports AbortController for the "Stop Generation" feature — any
 * in-flight /chat or /upload request can be cancelled by calling
 * abortActiveRequest().
 */

// Base URL of the FastAPI backend (runs locally on port 8000)
const API_BASE_URL = "http://127.0.0.1:8000";

// ---------------------------------------------------------------------------
// Abort Controller (shared across chat & upload)
// ---------------------------------------------------------------------------

/** @type {AbortController | null} */
let activeController = null;

/**
 * Abort the currently in-flight /chat or /upload request (if any).
 * Called by the "Stop ⏹" button in ChatInterface.
 */
export function abortActiveRequest() {
  if (activeController) {
    activeController.abort();
    activeController = null;
  }
}

// ---------------------------------------------------------------------------
// POST /chat — send conversation history, get AI explanation
// ---------------------------------------------------------------------------

/**
 * Send the full conversation history to the /chat endpoint and return the
 * AI's explanation.
 *
 * @param {Array<{role: string, content: string}>} chatHistory - The full
 *   conversation so far (user + assistant messages).
 * @returns {Promise<{explanation: string, audio_base64: string|null}>}
 * @throws {Error} - Re-throws with a user-friendly message on failure.
 */
export async function sendChatMessage(chatHistory) {
  // Create a fresh controller for this request
  activeController = new AbortController();
  const { signal } = activeController;

  try {
    const response = await fetch(`${API_BASE_URL}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages: chatHistory }),
      signal,
    });

    // If the backend returned an error status, surface the detail message
    if (!response.ok) {
      const errorData = await response.json().catch(() => null);
      throw new Error(
        errorData?.detail || `Server error (${response.status})`
      );
    }

    const data = await response.json();

    // Return the full object which now includes { explanation, audio_base64 }
    return data;
  } catch (error) {
    if (error.name === "AbortError") {
      throw new Error("Generation stopped by user.", { cause: error });
    }
    console.error("[api] sendChatMessage failed:", error);
    throw error;
  } finally {
    activeController = null;
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
        "Transcription request timed out. The model may be loading — please try again in 30 seconds.",
        { cause: error }
      );
    }

    // Network-level failure (backend unreachable, CORS blocked, etc.)
    // fetch() throws a TypeError with a vague "Failed to fetch" message.
    if (error instanceof TypeError) {
      console.error("[api] transcribeAudio network error:", error);
      throw new Error(
        "Could not reach the backend server. Please check that uvicorn is running on port 8000.",
        { cause: error }
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

// ---------------------------------------------------------------------------
// POST /upload — send file and optional prompt
// ---------------------------------------------------------------------------

/**
 * Upload a file (image or PDF) along with an optional text prompt.
 *
 * @param {File} file - The file to upload.
 * @param {string} prompt - Optional text prompt to accompany the file.
 * @param {boolean} forceVision - When true, forces the backend to process
 *   the PDF through the LLaVA → Qwen vision pipeline instead of plain-text
 *   extraction.  Useful for hybrid PDFs containing handwriting.
 * @returns {Promise<{explanation: string, audio_base64: string}>} - The AI's response.
 */
export async function uploadFile(file, prompt = "", forceVision = false) {
  // Create a fresh controller for this request
  activeController = new AbortController();
  const { signal } = activeController;

  try {
    const formData = new FormData();
    formData.append("file", file);
    if (prompt && prompt.trim() !== "") {
      formData.append("prompt", prompt.trim());
    }
    // Tell the backend whether to route through the vision pipeline
    formData.append("force_vision", forceVision ? "true" : "false");

    // Determine the API endpoint based on file type (Phase 4 Local Video support)
    const endpoint = file.type.startsWith("video/") ? "/video/upload" : "/upload";

    const response = await fetch(`${API_BASE_URL}${endpoint}`, {
      method: "POST",
      body: formData,
      signal,
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => null);
      throw new Error(
        errorData?.detail || `Upload failed (${response.status})`
      );
    }

    return await response.json();
  } catch (error) {
    if (error.name === "AbortError") {
      throw new Error("Generation stopped by user.", { cause: error });
    }
    console.error("[api] uploadFile failed:", error);
    throw error;
  } finally {
    activeController = null;
  }
}

// ---------------------------------------------------------------------------
// POST /youtube — send YouTube URL, get AI explanation of the transcript
// ---------------------------------------------------------------------------

/**
 * Send a YouTube URL to the /youtube endpoint.  The backend fetches the
 * video transcript and returns an AI-generated summary / explanation.
 *
 * @param {string} url - A YouTube video URL.
 * @returns {Promise<{explanation: string, audio_base64: string|null}>}
 * @throws {Error} - Re-throws with a user-friendly message on failure.
 */
export async function processYouTubeVideo(url) {
  // Create a fresh controller for this request
  activeController = new AbortController();
  const { signal } = activeController;

  try {
    const response = await fetch(`${API_BASE_URL}/youtube`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
      signal,
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => null);
      throw new Error(
        errorData?.detail || `YouTube processing failed (${response.status})`
      );
    }

    return await response.json();
  } catch (error) {
    if (error.name === "AbortError") {
      throw new Error("Generation stopped by user.", { cause: error });
    }
    console.error("[api] processYouTubeVideo failed:", error);
    throw error;
  } finally {
    activeController = null;
  }
}

// ---------------------------------------------------------------------------
// POST /execute-code — run Python code in the Docker sandbox
// ---------------------------------------------------------------------------

/**
 * Send code to the /execute-code endpoint for sandboxed execution
 * with self-correcting debugging (up to 3 attempts).
 *
 * @param {string} code - Source code to execute.
 * @param {string} language - "python" | "c" | "cpp"
 * @param {string} userInput - Optional stdin data (LeetCode-style pre-typed input)
 * @returns {Promise<{output: string, has_error: boolean, attempts: number, max_attempts: number, language: string, stderr: string|null, fixed_code: string|null}>}
 * @throws {Error} - Re-throws with a user-friendly message on failure.
 */
export async function executeCode(code, language = "python", userInput = "") {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 120_000);

  try {
    const body = { code, language };
    if (userInput) {
      body.user_input = userInput;
    }

    const response = await fetch(`${API_BASE_URL}/execute-code`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: controller.signal,
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => null);
      throw new Error(
        errorData?.detail || `Code execution failed (${response.status})`
      );
    }

    return await response.json();
  } catch (error) {
    if (error.name === "AbortError") {
      throw new Error(
        "Code execution timed out. The sandbox may be loading — please try again.",
        { cause: error }
      );
    }
    console.error("[api] executeCode failed:", error);
    throw error;
  } finally {
    clearTimeout(timeoutId);
  }
}

// ---------------------------------------------------------------------------
// POST /api/orchestrate — Magic Wand SSE Stream
// ---------------------------------------------------------------------------

/**
 * Triggers the Magic Wand debugger and streams SSE updates back.
 */
export async function orchestrateDebug(payload, onChunk, onDone, onError) {
  activeController = new AbortController();
  const { signal } = activeController;

  try {
    const response = await fetch(`${API_BASE_URL}/api/orchestrate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal,
    });

    if (!response.ok) {
      throw new Error(`Server error (${response.status})`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || ""; // keep the last incomplete line in buffer

      for (const line of lines) {
        if (!line.trim()) continue;
        try {
          const data = JSON.parse(line);
          onChunk(data);
        } catch (err) {
          console.error("Failed to parse SSE line:", line, err);
        }
      }
    }
    
    // Process remaining buffer
    if (buffer.trim()) {
      try {
        const data = JSON.parse(buffer);
        onChunk(data);
      } catch {
        // ignore
      }
    }

    onDone();

  } catch (error) {
    if (error.name === "AbortError") return;
    console.error("[api] orchestrateDebug failed:", error);
    onError(error);
  } finally {
    activeController = null;
  }
}

// ---------------------------------------------------------------------------
// POST /api/generate-quiz — Quiz Generation
// ---------------------------------------------------------------------------

/**
 * Generate a quiz from a video transcript.
 */
export async function generateQuiz(videoId, videoTitle, videoTranscript) {
  activeController = new AbortController();
  const { signal } = activeController;

  try {
    const response = await fetch(`${API_BASE_URL}/api/generate-quiz`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        video_id: videoId,
        video_title: videoTitle,
        video_transcript: videoTranscript,
      }),
      signal,
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => null);
      throw new Error(errorData?.detail || `Server error (${response.status})`);
    }

    const data = await response.json();
    return data.quiz;
  } catch (error) {
    if (error.name === "AbortError") {
      throw new Error("Quiz generation stopped.", { cause: error });
    }
    console.error("[api] generateQuiz failed:", error);
    throw error;
  } finally {
    activeController = null;
  }
}

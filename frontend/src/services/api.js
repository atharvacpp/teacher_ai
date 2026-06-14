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

/**
 * Common utility to read Server-Sent Events (SSE) from a fetch Response.
 *
 * @param {Response} response
 * @param {Object} callbacks
 * @param {Function} [callbacks.onChunk]
 * @param {Function} [callbacks.onAudio]
 * @param {Function} [callbacks.onTextComplete] - Fired when text is fully streamed; UI can unlock here
 * @param {Function} [callbacks.onTranscript]
 * @param {Function} [callbacks.onDone] - Fired once when the SSE connection closes
 * @param {Function} [callbacks.onStatus]
 */
async function readStream(response, {
  onChunk,
  onAudio,
  onTextComplete,
  onTranscript,
  onDone,
  onStatus,
  onSandboxArtifact,
}) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  let doneCallbackFired = false;
  let textCompleteFired = false;
  let streamError = null;

  const fireTextComplete = () => {
    if (!textCompleteFired) {
      textCompleteFired = true;
      if (onTextComplete) onTextComplete();
    }
  };

  const fireDone = () => {
    if (!doneCallbackFired) {
      doneCallbackFired = true;
      if (onDone) onDone();
    }
  };

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (let line of lines) {
        line = line.trim();
        if (!line) continue;

        let jsonStr = line;
        if (line.startsWith("data:")) {
          jsonStr = line.substring(5).trim();
        }

        if (!jsonStr) continue;

        try {
          const data = JSON.parse(jsonStr);
          if (data.type === "chunk") {
            if (onChunk) onChunk(data.content);
          } else if (data.type === "log" || data.type === "status") {
            if (onStatus) {
              onStatus(data.message || data.content);
            } else if (onChunk) {
              onChunk(`\n> _${data.message || data.content}_\n\n`);
            }
          } else if (data.type === "transcript") {
            if (onTranscript) onTranscript(data.content);
          } else if (data.type === "text_complete") {
            fireTextComplete();
          } else if (data.type === "audio") {
            const audioPayload = data.data || data.audio_base64;
            if (onAudio && audioPayload) onAudio(audioPayload);
          } else if (data.type === "error") {
            streamError = new Error(data.content || data.message);
          } else if (data.type === "sandbox_artifact") {
            if (onSandboxArtifact) onSandboxArtifact(data.artifact);
          } else if (data.type === "done") {
            fireTextComplete();
          }
        } catch (err) {
          if (onChunk && !jsonStr.startsWith("{")) {
            onChunk(jsonStr);
          } else {
            console.error("[api] Failed to parse stream chunk:", jsonStr);
          }
        }
      }
    }
  } finally {
    fireDone();
    reader.releaseLock();
  }

  if (streamError) {
    throw streamError;
  }
}

/**
 * Stream the conversation history to the /chat endpoint via SSE.
 *
 * @param {Array<{role: string, content: string}>} chatHistory
 * @param {Object|Function} callbacks - Callback map or legacy onChunk function
 * @param {Function} [callbacks.onChunk]
 * @param {Function} [callbacks.onTextComplete] - Unlock UI when text finishes
 * @param {Function} [callbacks.onAudio] - Late audio payload for a specific message
 * @param {Function} [callbacks.onDone] - Stream fully closed (after audio or error)
 */
export async function streamChatMessage(chatHistory, callbacks, onAudio, onDone) {
  const handlers = typeof callbacks === "function"
    ? { onChunk: callbacks, onAudio, onDone }
    : callbacks;

  activeController = new AbortController();
  const { signal } = activeController;

  try {
    const response = await fetch(`${API_BASE_URL}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages: chatHistory }),
      signal,
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => null);
      throw new Error(errorData?.detail || `Server error (${response.status})`);
    }

    await readStream(response, handlers);
  } catch (error) {
    if (error.name === "AbortError") {
      throw new Error("Generation stopped by user.", { cause: error });
    }
    console.error("[api] streamChatMessage failed:", error);
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
export async function uploadFile(file, prompt = "", forceVision = false, onChunk, onAudio, onTranscript, onDone, onStatus, onTextComplete) {
  activeController = new AbortController();
  const { signal } = activeController;

  try {
    const formData = new FormData();
    formData.append("file", file);
    if (prompt && prompt.trim() !== "") {
      formData.append("prompt", prompt.trim());
    }
    formData.append("force_vision", forceVision ? "true" : "false");

    const endpoint = file.type.startsWith("video/") ? "/video/upload" : "/upload";

    const response = await fetch(`${API_BASE_URL}${endpoint}`, {
      method: "POST",
      body: formData,
      signal,
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => null);
      throw new Error(errorData?.detail || `Upload failed (${response.status})`);
    }

    await readStream(response, { onChunk, onAudio, onTranscript, onDone, onStatus, onTextComplete });
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
export async function processYouTubeVideo(url, onChunk, onAudio, onTranscript, onDone, onStatus, onTextComplete) {
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
      throw new Error(errorData?.detail || `YouTube fetch failed (${response.status})`);
    }

    await readStream(response, { onChunk, onAudio, onTranscript, onDone, onStatus, onTextComplete });
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

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || ""; // keep the last incomplete line in buffer

        for (let line of lines) {
          line = line.trim();
          if (!line) continue;
          
          let jsonStr = line;
          if (line.startsWith("data:")) {
            jsonStr = line.substring(5).trim();
          }
          
          try {
            const data = JSON.parse(jsonStr);
            onChunk(data);
            if (data.type === "success" || data.type === "error") {
              return; // Fix: exit stream loop on terminal states
            }
          } catch (err) {
            console.error("Failed to parse SSE line:", jsonStr, err);
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
    } finally {
      onDone();
      reader.releaseLock();
    }

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

// ---------------------------------------------------------------------------
// POST /generate-lesson — Pipeline C
// ---------------------------------------------------------------------------

/**
 * Generate a comprehensive lesson via Pipeline C using a topic.
 */
export async function generateLesson(topic, onChunk, onAudio, onTranscript, onDone, onStatus, onTextComplete, onSandboxArtifact) {
  activeController = new AbortController();
  const { signal } = activeController;

  try {
    const response = await fetch(`${API_BASE_URL}/generate-lesson`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ topic }),
      signal,
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => null);
      throw new Error(errorData?.detail || `Server error (${response.status})`);
    }

    await readStream(response, { onChunk, onAudio, onTranscript, onDone, onStatus, onTextComplete, onSandboxArtifact });
  } catch (error) {
    if (error.name === "AbortError") {
      throw new Error("Generation stopped by user.", { cause: error });
    }
    console.error("[api] generateLesson failed:", error);
    throw error;
  } finally {
    activeController = null;
  }
}

// ---------------------------------------------------------------------------
// POST /api/ingest_memory — Upload file to AI Long-Term Memory
// ---------------------------------------------------------------------------

/**
 * Upload a file to be chunked, embedded, and stored in Pinecone vector DB.
 *
 * @param {File} file - The file to upload.
 * @returns {Promise<{status: string, message: string, chunks_created: number}>}
 */
export async function ingestMemory(file) {
  const formData = new FormData();
  formData.append("file", file);

  try {
    const response = await fetch(`${API_BASE_URL}/api/ingest_memory`, {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => null);
      throw new Error(errorData?.detail || `Upload failed (${response.status})`);
    }

    return await response.json();
  } catch (error) {
    console.error("[api] ingestMemory failed:", error);
    throw error;
  }
}


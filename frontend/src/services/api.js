/**
 * api.js — API service layer for ExplainAI frontend.
 *
 * Handles all HTTP communication with the FastAPI backend.
 * Centralised here so every component can import a single, clean function
 * instead of scattering fetch logic throughout the UI code.
 */

// Base URL of the FastAPI backend (runs locally on port 8000)
const API_BASE_URL = "http://127.0.0.1:8000";

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

    // Return only the explanation string to the caller
    return data.explanation;
  } catch (error) {
    // Network failures, JSON parse errors, etc.
    console.error("[api] sendChatMessage failed:", error);
    throw error;
  }
}

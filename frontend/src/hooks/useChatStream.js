/**
 * useChatStream.js — Decoupled SSE chat streaming hook.
 *
 * Text chunks stream into a targeted assistant message. When the backend
 * emits `text_complete`, the UI unlocks immediately. The hook keeps
 * reading the open SSE connection in the background until the late
 * `audio` chunk arrives, then patches only that message's audio field.
 */

import { useCallback, useRef } from "react";
import { streamChatMessage, abortActiveRequest } from "../services/api";

function createMessageId() {
  return globalThis.crypto?.randomUUID?.() ?? `msg-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export function useChatStream({ setMessages, setLoading, setStatusText }) {
  const activeTextRequestRef = useRef(null);

  const patchMessageById = useCallback((messageId, updater) => {
    setMessages((prev) =>
      prev.map((message) =>
        message.id === messageId
          ? typeof updater === "function"
            ? updater(message)
            : { ...message, ...updater }
          : message
      )
    );
  }, [setMessages]);

  const unlockIfCurrent = useCallback((requestId) => {
    if (activeTextRequestRef.current === requestId) {
      activeTextRequestRef.current = null;
      setLoading(false);
      setStatusText("");
    }
  }, [setLoading, setStatusText]);

  const streamAssistantReply = useCallback(async (chatHistory) => {
    const requestId = createMessageId();
    const assistantId = createMessageId();
    activeTextRequestRef.current = requestId;
    setLoading(true);
    setStatusText("");

    setMessages((prev) => [
      ...prev,
      {
        id: assistantId,
        role: "assistant",
        content: "",
        audio_base64: null,
        audioPending: true,
      },
    ]);

    try {
      await streamChatMessage(chatHistory, {
        onChunk: (chunk) => {
          patchMessageById(assistantId, (message) => ({
            ...message,
            content: message.content + chunk,
          }));
        },
        onTextComplete: () => {
          patchMessageById(assistantId, { audioPending: true });
          unlockIfCurrent(requestId);
        },
        onAudio: (audio) => {
          patchMessageById(assistantId, (message) => ({
            ...message,
            audio_base64: audio,
            audioPending: false,
          }));
        },
        onDone: () => {
          patchMessageById(assistantId, { audioPending: false });
        },
      });
    } catch (error) {
      unlockIfCurrent(requestId);
      patchMessageById(assistantId, { audioPending: false });
      throw error;
    }
  }, [patchMessageById, setLoading, setMessages, setStatusText, unlockIfCurrent]);

  const stopGeneration = useCallback(() => {
    abortActiveRequest();
    activeTextRequestRef.current = null;
    setLoading(false);
    setStatusText("");
  }, [setLoading, setStatusText]);

  return {
    streamAssistantReply,
    stopGeneration,
  };
}

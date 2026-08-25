import { useCallback } from "react";

import { refresh } from "../api/auth";
import { useAuthStore } from "../stores/authStore";
import { useChatStore, type ChatMessage } from "../stores/chatStore";

interface DoneEventPayload {
  done: true;
  conversation_id: string;
  rejected?: boolean;
  message_id?: string;
  model?: string;
  model_tier?: string;
  is_low_confidence?: boolean;
  from_cache?: boolean;
}

interface TokenEventPayload {
  token: string;
}

/**
 * Parses the `data: {...}\n\n` SSE event framing
 * `chat_routes.py::_format_token_event`/`_format_done_event` write, from a
 * fetch() response body -- a native EventSource can't be used here since
 * it's GET-only with no way to attach an Authorization header or a request
 * body, and this endpoint is POST (files/plan.md's Query Flow: the request
 * body is the message text).
 */
async function streamChatResponse(
  url: string,
  accessToken: string,
  body: unknown,
  onToken: (token: string) => void,
): Promise<DoneEventPayload> {
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${accessToken}`,
    },
    body: JSON.stringify(body),
  });

  if (response.status === 401) {
    const error = new Error("Unauthorized");
    error.name = "SSEUnauthorizedError";
    throw error;
  }
  if (!response.ok || !response.body) {
    throw new Error(`Chat request failed with status ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let donePayload: DoneEventPayload | null = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const events = buffer.split("\n\n");
    buffer = events.pop() ?? "";

    for (const rawEvent of events) {
      const line = rawEvent.trim();
      if (!line.startsWith("data:")) continue;
      const payload = JSON.parse(line.slice("data:".length).trim()) as
        TokenEventPayload | DoneEventPayload;
      if ("done" in payload) {
        donePayload = payload;
      } else {
        onToken(payload.token);
      }
    }
  }

  if (!donePayload) {
    throw new Error("Chat stream ended without a done event.");
  }
  return donePayload;
}

/** Sends a chat message and streams the assistant's response into chatStore. */
export function useSSE() {
  const addMessage = useChatStore((state) => state.addMessage);
  const appendToMessage = useChatStore((state) => state.appendToMessage);
  const markMessagePersisted = useChatStore((state) => state.markMessagePersisted);
  const setIsStreaming = useChatStore((state) => state.setIsStreaming);

  const sendMessage = useCallback(
    async (conversationId: string, content: string) => {
      const userMessage: ChatMessage = {
        id: crypto.randomUUID(),
        conversationId,
        role: "user",
        content,
        modelUsed: null,
        isPersisted: false,
      };
      addMessage(conversationId, userMessage);

      const assistantMessageId = crypto.randomUUID();
      addMessage(conversationId, {
        id: assistantMessageId,
        conversationId,
        role: "assistant",
        content: "",
        modelUsed: null,
        isPersisted: false,
      });

      const url = `${import.meta.env.VITE_API_BASE_URL}/api/chat/conversations/${conversationId}/messages`;
      const onToken = (token: string) => appendToMessage(conversationId, assistantMessageId, token);

      setIsStreaming(true);
      try {
        const { accessToken, refreshToken } = useAuthStore.getState();
        let donePayload: DoneEventPayload;
        try {
          donePayload = await streamChatResponse(url, accessToken ?? "", { content }, onToken);
        } catch (error) {
          // Same one-retry-after-refresh contract as client.ts's Axios
          // interceptor -- this call goes through fetch(), not apiClient,
          // so it needs its own copy of that logic.
          if (error instanceof Error && error.name === "SSEUnauthorizedError" && refreshToken) {
            const { access_token: newAccessToken } = await refresh(refreshToken);
            useAuthStore.getState().setAccessToken(newAccessToken);
            donePayload = await streamChatResponse(url, newAccessToken, { content }, onToken);
          } else {
            throw error;
          }
        }
        if (!donePayload.rejected && donePayload.message_id) {
          markMessagePersisted(conversationId, assistantMessageId, donePayload.message_id);
        }
      } catch {
        appendToMessage(
          conversationId,
          assistantMessageId,
          "Sorry, something went wrong reaching the server. Please try again.",
        );
      } finally {
        setIsStreaming(false);
      }
    },
    [addMessage, appendToMessage, markMessagePersisted, setIsStreaming],
  );

  return { sendMessage };
}

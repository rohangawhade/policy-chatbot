import { useEffect, useRef } from "react";

import { useChatStore, type ChatMessage } from "../../stores/chatStore";
import { StreamingMessage } from "./StreamingMessage";

// A stable reference for "no messages yet" -- returning a fresh `[]`
// literal from the selector below would give useSyncExternalStore a new
// array identity on every call, which it reads as "the store changed",
// which triggers another render, which calls the selector again... an
// infinite render loop, caught by actually running this in a browser
// (a real "Maximum update depth exceeded" crash, not a hypothetical).
const EMPTY_MESSAGES: ChatMessage[] = [];

export function ChatWindow() {
  const activeConversationId = useChatStore((state) => state.activeConversationId);
  const messages = useChatStore((state) =>
    activeConversationId
      ? (state.messagesByConversation[activeConversationId] ?? EMPTY_MESSAGES)
      : EMPTY_MESSAGES,
  );
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  if (!activeConversationId) {
    return (
      <div className="flex flex-1 items-center justify-center text-sm text-gray-400">
        Select or start a conversation to begin.
      </div>
    );
  }

  return (
    <div className="flex flex-1 flex-col gap-3 overflow-y-auto p-4">
      {messages.length === 0 && (
        <p className="text-sm text-gray-400">Ask a question about your benefits to get started.</p>
      )}
      {messages.map((message, index) => (
        <StreamingMessage
          key={message.id}
          message={message}
          isLastMessage={index === messages.length - 1}
        />
      ))}
      <div ref={bottomRef} />
    </div>
  );
}

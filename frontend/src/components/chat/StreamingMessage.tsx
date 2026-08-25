import type { ChatMessage } from "../../stores/chatStore";
import { useChatStore } from "../../stores/chatStore";
import { MessageBubble } from "./MessageBubble";

interface StreamingMessageProps {
  message: ChatMessage;
  isLastMessage: boolean;
}

/**
 * Wraps MessageBubble, deciding whether this specific message is the one
 * currently streaming tokens in (the last assistant message while
 * chatStore.isStreaming is true) -- keeps that decision out of ChatWindow,
 * which just renders a list.
 */
export function StreamingMessage({ message, isLastMessage }: StreamingMessageProps) {
  const isStreaming = useChatStore((state) => state.isStreaming);
  const isCurrentlyStreaming = isLastMessage && isStreaming && message.role === "assistant";
  return <MessageBubble message={message} isStreaming={isCurrentlyStreaming} />;
}

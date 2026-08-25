import type { ChatMessage } from "../../stores/chatStore";
import { FeedbackButtons } from "./FeedbackButtons";

// Matches backend/src/core/services/rag_service.py's RAGService._format_citations
// exactly -- citations are appended as plain text onto the message content,
// not a separate structured field, so this is the only way to split them
// back out for the collapsible display files/plan.md's Step 10.3 asks for.
const CITATION_MARKER = "\n\nSources: ";

function splitCitations(content: string): { body: string; sources: string[] } {
  const markerIndex = content.indexOf(CITATION_MARKER);
  if (markerIndex === -1) {
    return { body: content, sources: [] };
  }
  return {
    body: content.slice(0, markerIndex),
    sources: content
      .slice(markerIndex + CITATION_MARKER.length)
      .split("; ")
      .filter(Boolean),
  };
}

interface MessageBubbleProps {
  message: ChatMessage;
  isStreaming?: boolean;
}

export function MessageBubble({ message, isStreaming = false }: MessageBubbleProps) {
  const isUser = message.role === "user";
  const { body, sources } = splitCitations(message.content);

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[75%] rounded-lg px-4 py-2 text-sm whitespace-pre-wrap ${
          isUser ? "bg-blue-600 text-white" : "bg-gray-100 text-gray-900"
        }`}
      >
        {body}
        {isStreaming && <span className="ml-0.5 animate-pulse">▍</span>}

        {sources.length > 0 && (
          <details className="mt-2 text-xs opacity-80">
            <summary className="cursor-pointer select-none">Sources</summary>
            <ul className="mt-1 list-disc pl-4">
              {sources.map((source) => (
                <li key={source}>{source}</li>
              ))}
            </ul>
          </details>
        )}

        {!isUser && !isStreaming && message.isPersisted && (
          <div className="mt-2">
            <FeedbackButtons messageId={message.id} />
          </div>
        )}
      </div>
    </div>
  );
}

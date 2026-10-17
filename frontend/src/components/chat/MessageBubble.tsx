import ReactMarkdown from "react-markdown";
import rehypeRaw from "rehype-raw";
import rehypeSanitize from "rehype-sanitize";
import remarkGfm from "remark-gfm";

import type { ChatMessage } from "../../stores/chatStore";
import { FeedbackButtons } from "./FeedbackButtons";

// The assistant's `generate()` prompt asks for markdown (bold, GFM
// tables) -- remark-gfm is specifically needed for table syntax, which
// isn't part of base markdown. Child-selector classes (not the
// @tailwindcss/typography plugin, which this project doesn't otherwise
// use) style the handful of elements the system prompt actually
// produces. User messages are plain typed text, not LLM markdown, so
// they're rendered as-is below rather than through this.
const MARKDOWN_CLASSES =
  "[&_p]:mb-2 [&_p:last-child]:mb-0 [&_ul]:mb-2 [&_ul]:list-disc [&_ul]:pl-4 " +
  "[&_ol]:mb-2 [&_ol]:list-decimal [&_ol]:pl-4 [&_strong]:font-semibold " +
  "[&_table]:my-2 [&_table]:w-full [&_table]:border-collapse " +
  "[&_th]:border [&_th]:border-gray-300 [&_th]:bg-gray-200 [&_th]:px-2 [&_th]:py-1 [&_th]:text-left " +
  "[&_td]:border [&_td]:border-gray-300 [&_td]:px-2 [&_td]:py-1 " +
  "[&_a]:underline";

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
        className={`max-w-[75%] rounded-lg px-4 py-2 text-sm ${
          isUser ? "bg-blue-600 text-white whitespace-pre-wrap" : `bg-gray-100 text-gray-900 ${MARKDOWN_CLASSES}`
        }`}
      >
        {isUser ? (
          body
        ) : (
          // rehypeRaw parses the literal <br> tags the assistant's prompt
          // sometimes emits inside table cells (markdown has no other way
          // to break a line within a single cell); rehypeSanitize must run
          // after it to strip anything else, since the retrieved document
          // content this is ultimately grounded in isn't a fully trusted
          // input (uploaded by employers/admins, not just written by us).
          <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeRaw, rehypeSanitize]}>
            {body}
          </ReactMarkdown>
        )}
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

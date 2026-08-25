import { ChatInput } from "../components/chat/ChatInput";
import { ChatWindow } from "../components/chat/ChatWindow";
import { ConversationSidebar } from "../components/chat/ConversationSidebar";
import { useSSE } from "../hooks/useSSE";
import { useChatStore } from "../stores/chatStore";

export default function ChatPage() {
  const activeConversationId = useChatStore((state) => state.activeConversationId);
  const isStreaming = useChatStore((state) => state.isStreaming);
  const { sendMessage } = useSSE();

  function handleSend(content: string) {
    if (!activeConversationId) return;
    void sendMessage(activeConversationId, content);
  }

  return (
    <div className="flex h-screen">
      <ConversationSidebar />
      <div className="flex flex-1 flex-col">
        <ChatWindow />
        <ChatInput onSend={handleSend} disabled={!activeConversationId || isStreaming} />
      </div>
    </div>
  );
}

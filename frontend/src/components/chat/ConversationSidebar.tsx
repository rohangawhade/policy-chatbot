import { useEffect, useState } from "react";

import { createConversation, getConversationMessages, listConversations } from "../../api/chat";
import { useChatStore } from "../../stores/chatStore";

export function ConversationSidebar() {
  const conversations = useChatStore((state) => state.conversations);
  const activeConversationId = useChatStore((state) => state.activeConversationId);
  const setConversations = useChatStore((state) => state.setConversations);
  const addConversation = useChatStore((state) => state.addConversation);
  const setActiveConversation = useChatStore((state) => state.setActiveConversation);
  const setMessages = useChatStore((state) => state.setMessages);
  const [isLoading, setIsLoading] = useState(true);
  const [isCreating, setIsCreating] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      const list = await listConversations();
      if (cancelled) return;
      setConversations(list);
      if (list.length > 0) {
        await selectConversation(list[0].id);
      }
      setIsLoading(false);
    }

    load().catch(() => setIsLoading(false));
    return () => {
      cancelled = true;
    };
    // Runs once on mount to load the current user's conversation list --
    // the functions referenced (all Zustand setters, stable identities)
    // deliberately aren't in the dependency array.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function selectConversation(conversationId: string) {
    setActiveConversation(conversationId);
    const messages = await getConversationMessages(conversationId);
    setMessages(conversationId, messages);
  }

  async function handleNewConversation() {
    setIsCreating(true);
    try {
      const conversation = await createConversation();
      addConversation(conversation);
      setMessages(conversation.id, []);
      setActiveConversation(conversation.id);
    } finally {
      setIsCreating(false);
    }
  }

  return (
    <aside className="flex w-64 flex-col border-r border-gray-200 bg-gray-50">
      <div className="p-3">
        <button
          type="button"
          onClick={() => void handleNewConversation()}
          disabled={isCreating}
          className="w-full rounded-md bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          + New conversation
        </button>
      </div>
      <div className="flex-1 overflow-y-auto">
        {isLoading && <p className="p-3 text-sm text-gray-400">Loading...</p>}
        {!isLoading && conversations.length === 0 && (
          <p className="p-3 text-sm text-gray-400">No conversations yet.</p>
        )}
        {conversations.map((conversation) => (
          <button
            key={conversation.id}
            type="button"
            onClick={() => void selectConversation(conversation.id)}
            className={`block w-full truncate px-3 py-2 text-left text-sm ${
              conversation.id === activeConversationId
                ? "bg-blue-100 text-blue-700"
                : "text-gray-700 hover:bg-gray-100"
            }`}
          >
            {conversation.title ?? "New conversation"}
          </button>
        ))}
      </div>
    </aside>
  );
}

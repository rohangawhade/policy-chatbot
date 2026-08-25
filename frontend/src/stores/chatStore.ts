import { create } from "zustand";

// Mirrors backend/src/api/routes/chat_routes.py's ConversationResponse/MessageResponse.
export interface Conversation {
  id: string;
  employeeId: string;
  employerId: string;
  title: string | null;
}

export type MessageRole = "user" | "assistant";

export interface ChatMessage {
  id: string;
  conversationId: string;
  role: MessageRole;
  content: string;
  modelUsed: string | null;
}

interface ChatState {
  conversations: Conversation[];
  activeConversationId: string | null;
  messagesByConversation: Record<string, ChatMessage[]>;
  isStreaming: boolean;

  setConversations: (conversations: Conversation[]) => void;
  addConversation: (conversation: Conversation) => void;
  setActiveConversation: (conversationId: string | null) => void;
  setMessages: (conversationId: string, messages: ChatMessage[]) => void;
  addMessage: (conversationId: string, message: ChatMessage) => void;
  /** Append a streamed token to an existing message's content in place -- Step 10.3's SSE hook. */
  appendToMessage: (conversationId: string, messageId: string, tokenText: string) => void;
  setIsStreaming: (isStreaming: boolean) => void;
  reset: () => void;
}

const initialState = {
  conversations: [],
  activeConversationId: null,
  messagesByConversation: {},
  isStreaming: false,
} satisfies Pick<
  ChatState,
  "conversations" | "activeConversationId" | "messagesByConversation" | "isStreaming"
>;

export const useChatStore = create<ChatState>((set) => ({
  ...initialState,

  setConversations: (conversations) => set({ conversations }),

  addConversation: (conversation) =>
    set((state) => ({ conversations: [...state.conversations, conversation] })),

  setActiveConversation: (conversationId) => set({ activeConversationId: conversationId }),

  setMessages: (conversationId, messages) =>
    set((state) => ({
      messagesByConversation: { ...state.messagesByConversation, [conversationId]: messages },
    })),

  addMessage: (conversationId, message) =>
    set((state) => ({
      messagesByConversation: {
        ...state.messagesByConversation,
        [conversationId]: [...(state.messagesByConversation[conversationId] ?? []), message],
      },
    })),

  appendToMessage: (conversationId, messageId, tokenText) =>
    set((state) => {
      const messages = state.messagesByConversation[conversationId];
      if (!messages) {
        return state;
      }
      return {
        messagesByConversation: {
          ...state.messagesByConversation,
          [conversationId]: messages.map((message) =>
            message.id === messageId
              ? { ...message, content: message.content + tokenText }
              : message,
          ),
        },
      };
    }),

  setIsStreaming: (isStreaming) => set({ isStreaming }),

  reset: () => set({ ...initialState }),
}));

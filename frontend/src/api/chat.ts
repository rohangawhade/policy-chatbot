import type { ChatMessage, Conversation, MessageRole } from "../stores/chatStore";
import { apiClient } from "./client";

// Mirrors backend/src/api/routes/chat_routes.py's response schemas.
interface ConversationResponseDto {
  id: string;
  employee_id: string;
  employer_id: string;
  title: string | null;
}

interface MessageResponseDto {
  id: string;
  conversation_id: string;
  role: MessageRole;
  content: string;
  model_used: string | null;
}

function toConversation(dto: ConversationResponseDto): Conversation {
  return {
    id: dto.id,
    employeeId: dto.employee_id,
    employerId: dto.employer_id,
    title: dto.title,
  };
}

function toMessage(dto: MessageResponseDto): ChatMessage {
  return {
    id: dto.id,
    conversationId: dto.conversation_id,
    role: dto.role,
    content: dto.content,
    modelUsed: dto.model_used,
    // Came straight from the backend -- it exists as a row by definition.
    isPersisted: true,
  };
}

export async function createConversation(): Promise<Conversation> {
  const response = await apiClient.post<ConversationResponseDto>("/api/chat/conversations");
  return toConversation(response.data);
}

export async function listConversations(): Promise<Conversation[]> {
  const response = await apiClient.get<ConversationResponseDto[]>("/api/chat/conversations");
  return response.data.map(toConversation);
}

export async function getConversationMessages(conversationId: string): Promise<ChatMessage[]> {
  const response = await apiClient.get<MessageResponseDto[]>(
    `/api/chat/conversations/${conversationId}/messages`,
  );
  return response.data.map(toMessage);
}

// Mirrors backend/src/api/routes/feedback_routes.py's FeedbackRating values.
// Lives here, not a dedicated api/feedback.ts -- files/plan.md's frontend
// file tree doesn't list one, and feedback only ever attaches to a chat
// message (FeedbackButtons.tsx), so it's scoped with the rest of chat.
export type FeedbackRating = "thumbs_up" | "thumbs_down";

export async function submitFeedback(messageId: string, rating: FeedbackRating): Promise<void> {
  await apiClient.post("/api/feedback", { message_id: messageId, rating });
}

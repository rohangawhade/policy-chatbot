import { create } from "zustand";
import type { PolicyType } from "../api/documents";

// Mirrors document_routes.py's DocumentListItemResponse -- the shape
// GET /api/documents actually returns (see api/documents.ts's
// DocumentListItemDto). Upload/status responses carry a different, smaller
// set of fields and are not stored here; DocumentUpload.tsx refetches the
// list after a successful upload instead of merging a partial shape in.
export interface Document {
  id: string;
  employerId: string;
  title: string;
  policyType: PolicyType | null;
  status: "processing" | "ready" | "failed";
  version: number;
}

interface DocumentState {
  documents: Document[];
  setDocuments: (documents: Document[]) => void;
  addDocument: (document: Document) => void;
  updateDocument: (documentId: string, updates: Partial<Document>) => void;
  removeDocument: (documentId: string) => void;
  reset: () => void;
}

const initialState = {
  documents: [],
} satisfies Pick<DocumentState, "documents">;

export const useDocumentStore = create<DocumentState>((set) => ({
  ...initialState,

  setDocuments: (documents) => set({ documents }),

  addDocument: (document) => set((state) => ({ documents: [...state.documents, document] })),

  updateDocument: (documentId, updates) =>
    set((state) => ({
      documents: state.documents.map((doc) =>
        doc.id === documentId ? { ...doc, ...updates } : doc,
      ),
    })),

  removeDocument: (documentId) =>
    set((state) => ({ documents: state.documents.filter((doc) => doc.id !== documentId) })),

  reset: () => set({ ...initialState }),
}));

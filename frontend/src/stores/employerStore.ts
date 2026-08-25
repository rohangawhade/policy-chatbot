import { create } from "zustand";

// Mirrors backend/src/core/domain/employer.py's Employer.
export interface Employer {
  id: string;
  name: string;
  isActive: boolean;
}

interface EmployerState {
  // Admin's view: every employer (Step 10.4's EmployerManagement).
  employers: Employer[];
  // An employer-role user's own tenant id (core/domain/employee.py's employer_id).
  currentEmployerId: string | null;

  setEmployers: (employers: Employer[]) => void;
  upsertEmployer: (employer: Employer) => void;
  removeEmployer: (employerId: string) => void;
  setCurrentEmployerId: (employerId: string | null) => void;
  reset: () => void;
}

const initialState = {
  employers: [],
  currentEmployerId: null,
} satisfies Pick<EmployerState, "employers" | "currentEmployerId">;

export const useEmployerStore = create<EmployerState>((set) => ({
  ...initialState,

  setEmployers: (employers) => set({ employers }),

  upsertEmployer: (employer) =>
    set((state) => {
      const existingIndex = state.employers.findIndex((e) => e.id === employer.id);
      if (existingIndex === -1) {
        return { employers: [...state.employers, employer] };
      }
      const employers = [...state.employers];
      employers[existingIndex] = employer;
      return { employers };
    }),

  removeEmployer: (employerId) =>
    set((state) => ({ employers: state.employers.filter((e) => e.id !== employerId) })),

  setCurrentEmployerId: (employerId) => set({ currentEmployerId: employerId }),

  reset: () => set({ ...initialState }),
}));

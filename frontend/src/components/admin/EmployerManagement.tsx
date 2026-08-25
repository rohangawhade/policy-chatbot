import { useEffect, useState } from "react";
import {
  createEmployer,
  deactivateEmployer,
  listEmployers,
  updateEmployer,
} from "../../api/employers";
import { useEmployerStore } from "../../stores/employerStore";

export default function EmployerManagement() {
  const employers = useEmployerStore((state) => state.employers);
  const setEmployers = useEmployerStore((state) => state.setEmployers);
  const upsertEmployer = useEmployerStore((state) => state.upsertEmployer);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [newEmployerName, setNewEmployerName] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingName, setEditingName] = useState("");

  useEffect(() => {
    const loadEmployers = async () => {
      try {
        const data = await listEmployers();
        setEmployers(
          data.map((emp) => ({
            id: emp.id,
            name: emp.name,
            isActive: emp.is_active,
          })),
        );
        setError(null);
      } catch (err) {
        const message = err instanceof Error ? err.message : "Failed to load employers";
        setError(message);
      } finally {
        setLoading(false);
      }
    };

    loadEmployers();
  }, [setEmployers]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newEmployerName.trim()) {
      setError("Employer name is required");
      return;
    }

    setIsCreating(true);
    setError(null);

    try {
      const newEmp = await createEmployer(newEmployerName);
      upsertEmployer({
        id: newEmp.id,
        name: newEmp.name,
        isActive: newEmp.is_active,
      });
      setNewEmployerName("");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to create employer";
      setError(message);
    } finally {
      setIsCreating(false);
    }
  };

  const handleEdit = async (employerId: string, newName: string) => {
    if (!newName.trim()) {
      setError("Employer name is required");
      return;
    }

    try {
      const updated = await updateEmployer(employerId, { name: newName });
      upsertEmployer({
        id: updated.id,
        name: updated.name,
        isActive: updated.is_active,
      });
      setEditingId(null);
      setError(null);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to update employer";
      setError(message);
    }
  };

  const handleDeactivate = async (employerId: string) => {
    if (!confirm("Deactivate this employer? This cannot be undone.")) return;

    try {
      await deactivateEmployer(employerId);
      upsertEmployer({
        ...employers.find((e) => e.id === employerId)!,
        isActive: false,
      });
      setError(null);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to deactivate employer";
      setError(message);
    }
  };

  if (loading) {
    return (
      <div className="rounded-lg border border-gray-200 bg-white p-6">
        <h2 className="mb-4 text-lg font-semibold">Employer Management</h2>
        <div className="text-center text-gray-500">Loading employers...</div>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-6">
      <h2 className="mb-4 text-lg font-semibold">Employer Management</h2>

      {error && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 p-4 text-red-700">
          {error}
        </div>
      )}

      {/* Create Employer Form */}
      <form onSubmit={handleCreate} className="mb-6 rounded-lg bg-gray-50 p-4">
        <h3 className="mb-3 font-medium text-gray-900">Create New Employer</h3>
        <div className="flex gap-2">
          <input
            type="text"
            placeholder="Employer name"
            value={newEmployerName}
            onChange={(e) => setNewEmployerName(e.target.value)}
            className="flex-1 rounded border border-gray-300 px-3 py-2"
            disabled={isCreating}
          />
          <button
            type="submit"
            disabled={isCreating}
            className="rounded bg-blue-600 px-4 py-2 text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {isCreating ? "Creating..." : "Create"}
          </button>
        </div>
      </form>

      {/* Employers List */}
      {employers.length === 0 ? (
        <div className="text-center text-gray-500">No employers yet</div>
      ) : (
        <div className="space-y-2">
          {employers.map((employer) => (
            <div
              key={employer.id}
              className="flex items-center justify-between rounded-lg border border-gray-200 p-4"
            >
              {editingId === employer.id ? (
                <div className="flex flex-1 gap-2">
                  <input
                    type="text"
                    value={editingName}
                    onChange={(e) => setEditingName(e.target.value)}
                    className="flex-1 rounded border border-gray-300 px-3 py-2"
                    autoFocus
                  />
                  <button
                    onClick={() => handleEdit(employer.id, editingName)}
                    className="rounded bg-green-600 px-3 py-2 text-white hover:bg-green-700"
                  >
                    Save
                  </button>
                  <button
                    onClick={() => setEditingId(null)}
                    className="rounded bg-gray-300 px-3 py-2 text-gray-700 hover:bg-gray-400"
                  >
                    Cancel
                  </button>
                </div>
              ) : (
                <>
                  <div className="flex-1">
                    <p className="font-medium text-gray-900">{employer.name}</p>
                    <p
                      className={`text-sm ${
                        employer.isActive ? "text-green-600" : "text-gray-500"
                      }`}
                    >
                      {employer.isActive ? "Active" : "Deactivated"}
                    </p>
                  </div>
                  <div className="flex gap-2">
                    {employer.isActive && (
                      <>
                        <button
                          onClick={() => {
                            setEditingId(employer.id);
                            setEditingName(employer.name);
                          }}
                          className="text-sm text-blue-600 hover:text-blue-800"
                        >
                          Edit
                        </button>
                        <button
                          onClick={() => handleDeactivate(employer.id)}
                          className="text-sm text-red-600 hover:text-red-800"
                        >
                          Deactivate
                        </button>
                      </>
                    )}
                  </div>
                </>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

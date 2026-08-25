import { useEffect, useState } from "react";
import {
  deactivateEmployee,
  inviteEmployee,
  listEmployees,
  updateEmployee,
  type EmployeeResponseDto,
} from "../../api/employees";

// "Invite" (plan.md) is direct account creation with a temporary
// password -- see api/employees.ts's `inviteEmployee` docstring for why
// (no email/SMTP integration exists anywhere in this app).
export default function UserManagement() {
  const [employees, setEmployees] = useState<EmployeeResponseDto[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [isInviting, setIsInviting] = useState(false);
  const [newEmail, setNewEmail] = useState("");
  const [newFullName, setNewFullName] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newRole, setNewRole] = useState<"employee" | "employer">("employee");

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingName, setEditingName] = useState("");

  useEffect(() => {
    listEmployees()
      .then(setEmployees)
      .catch((err) => {
        const message = err instanceof Error ? err.message : "Failed to load employees";
        setError(message);
      })
      .finally(() => setLoading(false));
  }, []);

  const handleInvite = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newEmail.trim() || !newFullName.trim() || !newPassword.trim()) {
      setError("Email, full name, and a temporary password are all required");
      return;
    }

    setIsInviting(true);
    setError(null);
    try {
      const created = await inviteEmployee({
        email: newEmail,
        password: newPassword,
        fullName: newFullName,
        role: newRole,
      });
      setEmployees((prev) => [...prev, created]);
      setNewEmail("");
      setNewFullName("");
      setNewPassword("");
      setNewRole("employee");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to invite employee";
      setError(message);
    } finally {
      setIsInviting(false);
    }
  };

  const handleRename = async (employeeId: string) => {
    if (!editingName.trim()) {
      setError("Name is required");
      return;
    }
    try {
      const updated = await updateEmployee(employeeId, { full_name: editingName });
      setEmployees((prev) => prev.map((e) => (e.id === employeeId ? updated : e)));
      setEditingId(null);
      setError(null);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to update employee";
      setError(message);
    }
  };

  const handleDeactivate = async (employeeId: string) => {
    if (!confirm("Deactivate this employee?")) return;
    try {
      await deactivateEmployee(employeeId);
      setEmployees((prev) =>
        prev.map((e) => (e.id === employeeId ? { ...e, is_active: false } : e)),
      );
      setError(null);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to deactivate employee";
      setError(message);
    }
  };

  if (loading) {
    return <div className="text-center text-gray-500">Loading employees...</div>;
  }

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-6">
      <h2 className="mb-4 text-lg font-semibold">Employee Management</h2>

      {error && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 p-4 text-red-700">
          {error}
        </div>
      )}

      <form onSubmit={handleInvite} className="mb-6 space-y-3 rounded-lg bg-gray-50 p-4">
        <h3 className="font-medium text-gray-900">Invite Employee</h3>
        <div className="flex flex-wrap gap-2">
          <input
            type="email"
            placeholder="Email"
            value={newEmail}
            onChange={(e) => setNewEmail(e.target.value)}
            className="rounded border border-gray-300 px-3 py-2"
            disabled={isInviting}
          />
          <input
            type="text"
            placeholder="Full name"
            value={newFullName}
            onChange={(e) => setNewFullName(e.target.value)}
            className="rounded border border-gray-300 px-3 py-2"
            disabled={isInviting}
          />
          <input
            type="password"
            placeholder="Temporary password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            className="rounded border border-gray-300 px-3 py-2"
            disabled={isInviting}
          />
          <select
            value={newRole}
            onChange={(e) => setNewRole(e.target.value as "employee" | "employer")}
            className="rounded border border-gray-300 px-3 py-2"
            disabled={isInviting}
          >
            <option value="employee">Employee</option>
            <option value="employer">Employer contact</option>
          </select>
          <button
            type="submit"
            disabled={isInviting}
            className="rounded bg-blue-600 px-4 py-2 text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {isInviting ? "Inviting..." : "Invite"}
          </button>
        </div>
      </form>

      {employees.length === 0 ? (
        <div className="text-center text-gray-500">No employees yet</div>
      ) : (
        <div className="space-y-2">
          {employees.map((employee) => (
            <div
              key={employee.id}
              className="flex items-center justify-between rounded-lg border border-gray-200 p-4"
            >
              {editingId === employee.id ? (
                <div className="flex flex-1 gap-2">
                  <input
                    type="text"
                    value={editingName}
                    onChange={(e) => setEditingName(e.target.value)}
                    className="flex-1 rounded border border-gray-300 px-3 py-2"
                    autoFocus
                  />
                  <button
                    onClick={() => handleRename(employee.id)}
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
                  <div>
                    <p className="font-medium text-gray-900">{employee.full_name}</p>
                    <p className="text-sm text-gray-500">
                      {employee.email} · {employee.role}
                    </p>
                    <p
                      className={`text-sm ${employee.is_active ? "text-green-600" : "text-gray-500"}`}
                    >
                      {employee.is_active ? "Active" : "Deactivated"}
                    </p>
                  </div>
                  {employee.is_active && (
                    <div className="flex gap-2">
                      <button
                        onClick={() => {
                          setEditingId(employee.id);
                          setEditingName(employee.full_name);
                        }}
                        className="text-sm text-blue-600 hover:text-blue-800"
                      >
                        Edit
                      </button>
                      <button
                        onClick={() => handleDeactivate(employee.id)}
                        className="text-sm text-red-600 hover:text-red-800"
                      >
                        Deactivate
                      </button>
                    </div>
                  )}
                </>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

import { useEffect, useState } from "react";
import {
  listPolicies,
  listPolicyEnrollments,
  type EnrolledEmployeeDto,
  type PolicyResponseDto,
} from "../../api/policies";

const POLICY_TYPE_LABELS: Record<string, string> = {
  health: "Health",
  dental: "Dental",
  vision: "Vision",
  life: "Life",
  disability: "Disability",
};

export default function PolicyOverview() {
  const [policies, setPolicies] = useState<PolicyResponseDto[]>([]);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [enrollments, setEnrollments] = useState<Record<string, EnrolledEmployeeDto[]>>({});
  const [enrollmentsLoading, setEnrollmentsLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    listPolicies()
      .then(setPolicies)
      .catch((err) => {
        const message = err instanceof Error ? err.message : "Failed to load policies";
        setError(message);
      })
      .finally(() => setLoading(false));
  }, []);

  const toggleExpanded = async (policyId: string) => {
    if (expandedId === policyId) {
      setExpandedId(null);
      return;
    }
    setExpandedId(policyId);
    if (!enrollments[policyId]) {
      setEnrollmentsLoading(policyId);
      try {
        const enrolled = await listPolicyEnrollments(policyId);
        setEnrollments((prev) => ({ ...prev, [policyId]: enrolled }));
        setError(null);
      } catch (err) {
        const message = err instanceof Error ? err.message : "Failed to load enrollments";
        setError(message);
      } finally {
        setEnrollmentsLoading(null);
      }
    }
  };

  if (loading) {
    return <div className="text-center text-gray-500">Loading policies...</div>;
  }

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-6">
      <h2 className="mb-4 text-lg font-semibold">Policy Overview</h2>
      <p className="mb-4 text-sm text-gray-500">
        Every policy under your organization — expand a row to see which employees are
        enrolled.
      </p>

      {error && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 p-4 text-red-700">
          {error}
        </div>
      )}

      {policies.length === 0 ? (
        <p className="text-center text-gray-500">No policies configured yet</p>
      ) : (
        <div className="space-y-2">
          {policies.map((policy) => {
            const isExpanded = expandedId === policy.id;
            const enrolled = enrollments[policy.id];
            return (
              <div key={policy.id} className="rounded-lg border border-gray-200">
                <button
                  onClick={() => toggleExpanded(policy.id)}
                  className="flex w-full items-center justify-between px-4 py-3 text-left"
                >
                  <div>
                    <p className="font-medium text-gray-900">{policy.name}</p>
                    <p className="text-sm text-gray-500">
                      {POLICY_TYPE_LABELS[policy.policy_type] ?? policy.policy_type}
                      {policy.description ? ` · ${policy.description}` : ""}
                    </p>
                  </div>
                  <span className="text-sm text-gray-400">{isExpanded ? "Hide" : "Show"}</span>
                </button>

                {isExpanded && (
                  <div className="border-t border-gray-100 px-4 py-3">
                    {enrollmentsLoading === policy.id ? (
                      <p className="text-sm text-gray-500">Loading enrolled employees...</p>
                    ) : !enrolled || enrolled.length === 0 ? (
                      <p className="text-sm text-gray-500">No employees enrolled</p>
                    ) : (
                      <table className="w-full">
                        <thead>
                          <tr className="border-b border-gray-200 text-left text-sm font-medium text-gray-600">
                            <th className="pb-2">Employee</th>
                            <th className="pb-2">Email</th>
                            <th className="pb-2">Status</th>
                          </tr>
                        </thead>
                        <tbody>
                          {enrolled.map((employee) => (
                            <tr key={employee.employee_id} className="border-b border-gray-100">
                              <td className="py-2 pr-4">{employee.full_name}</td>
                              <td className="py-2 pr-4 text-gray-600">{employee.email}</td>
                              <td className="py-2">
                                <span
                                  className={
                                    employee.is_active ? "text-green-600" : "text-gray-500"
                                  }
                                >
                                  {employee.is_active ? "Enrolled" : "Unenrolled"}
                                </span>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

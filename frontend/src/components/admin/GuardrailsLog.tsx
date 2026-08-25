import { useEffect, useState } from "react";
import { listGuardrailRejections, type GuardrailRejectionItemDto } from "../../api/admin";
import { useEmployerStore } from "../../stores/employerStore";

export default function GuardrailsLog() {
  const employers = useEmployerStore((state) => state.employers);
  const [rejections, setRejections] = useState<GuardrailRejectionItemDto[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      try {
        setRejections(await listGuardrailRejections());
        setError(null);
      } catch (err) {
        const message = err instanceof Error ? err.message : "Failed to load guardrail rejections";
        setError(message);
      } finally {
        setLoading(false);
      }
    };

    load();
  }, []);

  const employerName = (id: string) => employers.find((e) => e.id === id)?.name ?? id;

  if (loading) {
    return <div className="text-center text-gray-500">Loading guardrail rejections...</div>;
  }

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-6">
      <h2 className="mb-4 text-lg font-semibold">Guardrails Log</h2>
      <p className="mb-4 text-sm text-gray-500">
        Rejected queries — use this to spot false positives (legitimate questions wrongly
        blocked) and tune the guardrails.
      </p>

      {error && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 p-4 text-red-700">
          {error}
        </div>
      )}

      {rejections.length === 0 ? (
        <p className="text-center text-gray-500">No rejected queries</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-gray-200 text-left text-sm font-medium text-gray-600">
                <th className="pb-2">Query</th>
                <th className="pb-2">Reason</th>
                <th className="pb-2">Employer</th>
                <th className="pb-2">When</th>
              </tr>
            </thead>
            <tbody>
              {rejections.map((rejection) => (
                <tr key={rejection.id} className="border-b border-gray-100">
                  <td className="max-w-xs truncate py-2 pr-4">{rejection.query_text}</td>
                  <td className="py-2 pr-4 text-gray-600">{rejection.rejection_reason}</td>
                  <td className="py-2 pr-4">{employerName(rejection.employer_id)}</td>
                  <td className="py-2 text-gray-500">
                    {new Date(rejection.created_at).toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

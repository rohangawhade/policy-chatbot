import { useEffect, useMemo, useState } from "react";
import { listUnansweredQueries, type FlaggedResponseItemDto } from "../../api/admin";
import { useEmployerStore, type Employer } from "../../stores/employerStore";

const POLICY_TYPE_LABELS: Record<string, string> = {
  health: "Health",
  dental: "Dental",
  vision: "Vision",
  life: "Life",
  disability: "Disability",
};

interface GroupedByEmployer {
  employerId: string;
  employerName: string;
  byPolicyType: { policyType: string; queries: FlaggedResponseItemDto[] }[];
}

// plan.md asks for these "grouped by employer and policy type" -- the
// backend returns a flat list (GET /api/admin/unanswered-queries), so the
// grouping happens here rather than adding a second, differently-shaped
// backend endpoint for what's purely a display concern.
function groupQueries(
  queries: FlaggedResponseItemDto[],
  employers: Employer[],
): GroupedByEmployer[] {
  const byEmployer = new Map<string, FlaggedResponseItemDto[]>();
  for (const query of queries) {
    const existing = byEmployer.get(query.employer_id) ?? [];
    existing.push(query);
    byEmployer.set(query.employer_id, existing);
  }

  return Array.from(byEmployer.entries())
    .map(([employerId, employerQueries]) => {
      const byPolicyType = new Map<string, FlaggedResponseItemDto[]>();
      for (const query of employerQueries) {
        const key = query.policy_type ?? "unknown";
        const existing = byPolicyType.get(key) ?? [];
        existing.push(query);
        byPolicyType.set(key, existing);
      }
      return {
        employerId,
        employerName: employers.find((e) => e.id === employerId)?.name ?? employerId,
        byPolicyType: Array.from(byPolicyType.entries())
          .map(([policyType, queries]) => ({ policyType, queries }))
          .sort((a, b) => b.queries.length - a.queries.length),
      };
    })
    .sort((a, b) => b.byPolicyType.flatMap((g) => g.queries).length - a.byPolicyType.flatMap((g) => g.queries).length);
}

export default function UnansweredQueries() {
  const employers = useEmployerStore((state) => state.employers);
  const [queries, setQueries] = useState<FlaggedResponseItemDto[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      try {
        setQueries(await listUnansweredQueries());
        setError(null);
      } catch (err) {
        const message = err instanceof Error ? err.message : "Failed to load unanswered queries";
        setError(message);
      } finally {
        setLoading(false);
      }
    };

    load();
  }, []);

  const grouped = useMemo(() => groupQueries(queries, employers), [queries, employers]);

  if (loading) {
    return <div className="text-center text-gray-500">Loading unanswered queries...</div>;
  }

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-6">
      <h2 className="mb-4 text-lg font-semibold">Unanswered Queries</h2>
      <p className="mb-4 text-sm text-gray-500">
        Queries where the bot couldn't find enough context — grouped by employer and policy
        type to reveal document corpus gaps.
      </p>

      {error && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 p-4 text-red-700">
          {error}
        </div>
      )}

      {grouped.length === 0 ? (
        <p className="text-center text-gray-500">No unanswered queries</p>
      ) : (
        <div className="space-y-6">
          {grouped.map((group) => (
            <div key={group.employerId}>
              <h3 className="mb-2 font-medium text-gray-900">{group.employerName}</h3>
              <div className="space-y-3 pl-4">
                {group.byPolicyType.map((sub) => (
                  <div key={sub.policyType}>
                    <p className="mb-1 text-sm font-medium text-gray-600">
                      {POLICY_TYPE_LABELS[sub.policyType] ?? "Unknown / general"} (
                      {sub.queries.length})
                    </p>
                    <ul className="space-y-1 pl-4 text-sm text-gray-700">
                      {sub.queries.map((query) => (
                        <li key={query.id} className="list-disc">
                          {query.query_text}
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

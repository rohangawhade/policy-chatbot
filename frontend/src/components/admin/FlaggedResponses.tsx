import { useEffect, useState } from "react";
import {
  listFlaggedResponses,
  updateFlaggedResponse,
  type FlaggedResponseItemDto,
} from "../../api/admin";

// plan.md's Step 10.6 bullet asks for "reviewed"/"false positive"/"needs
// document update" actions, but the backend only accepts reviewed/
// dismissed/escalated (admin_routes.py's `_TERMINAL_FLAG_STATUSES` --
// pending_review is the initial state, never a target). Mapped here:
// dismissed reads as "this flag was a false positive", escalated reads as
// "this needs follow-up work, e.g. a document update".
const STATUS_LABELS: Record<FlaggedResponseItemDto["status"], string> = {
  pending_review: "Pending Review",
  reviewed: "Reviewed",
  dismissed: "False Positive",
  escalated: "Needs Document Update",
};

const STATUS_STYLES: Record<FlaggedResponseItemDto["status"], string> = {
  pending_review: "bg-yellow-100 text-yellow-800",
  reviewed: "bg-blue-100 text-blue-800",
  dismissed: "bg-gray-100 text-gray-700",
  escalated: "bg-red-100 text-red-800",
};

export default function FlaggedResponses() {
  const [items, setItems] = useState<FlaggedResponseItemDto[]>([]);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [updatingId, setUpdatingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      try {
        setItems(await listFlaggedResponses());
        setError(null);
      } catch (err) {
        const message = err instanceof Error ? err.message : "Failed to load flagged responses";
        setError(message);
      } finally {
        setLoading(false);
      }
    };

    load();
  }, []);

  const handleUpdate = async (id: string, status: "reviewed" | "dismissed" | "escalated") => {
    setUpdatingId(id);
    try {
      const updated = await updateFlaggedResponse(id, status);
      setItems((prev) => prev.map((item) => (item.id === id ? updated : item)));
      setError(null);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to update flagged response";
      setError(message);
    } finally {
      setUpdatingId(null);
    }
  };

  if (loading) {
    return <div className="text-center text-gray-500">Loading flagged responses...</div>;
  }

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-6">
      <h2 className="mb-4 text-lg font-semibold">Flagged Responses</h2>
      {error && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 p-4 text-red-700">
          {error}
        </div>
      )}

      {items.length === 0 ? (
        <p className="text-center text-gray-500">No flagged responses</p>
      ) : (
        <div className="space-y-2">
          {items.map((item) => {
            const isExpanded = expandedId === item.id;
            return (
              <div key={item.id} className="rounded-lg border border-gray-200">
                <button
                  onClick={() => setExpandedId(isExpanded ? null : item.id)}
                  className="flex w-full items-center justify-between px-4 py-3 text-left"
                >
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium text-gray-900">{item.query_text}</p>
                    <p className="text-sm text-gray-500">
                      {new Date(item.created_at).toLocaleString()}
                      {item.top_similarity_score !== null &&
                        ` · similarity ${item.top_similarity_score.toFixed(2)}`}
                    </p>
                  </div>
                  <span
                    className={`ml-4 shrink-0 rounded-full px-3 py-1 text-sm font-medium ${STATUS_STYLES[item.status]}`}
                  >
                    {STATUS_LABELS[item.status]}
                  </span>
                </button>

                {isExpanded && (
                  <div className="border-t border-gray-100 px-4 py-3">
                    <dl className="space-y-2 text-sm">
                      <div>
                        <dt className="font-medium text-gray-700">Query</dt>
                        <dd className="text-gray-600">{item.query_text}</dd>
                      </div>
                      <div>
                        <dt className="font-medium text-gray-700">Generated response</dt>
                        <dd className="text-gray-600">{item.response_text ?? "(unavailable)"}</dd>
                      </div>
                      <div>
                        <dt className="font-medium text-gray-700">Model used</dt>
                        <dd className="text-gray-600">{item.model_used ?? "unknown"}</dd>
                      </div>
                      <div>
                        <dt className="font-medium text-gray-700">Top retrieved-chunk similarity</dt>
                        <dd className="text-gray-600">
                          {item.top_similarity_score !== null
                            ? item.top_similarity_score.toFixed(3)
                            : "n/a"}
                        </dd>
                      </div>
                    </dl>

                    <div className="mt-4 flex gap-2">
                      <button
                        onClick={() => handleUpdate(item.id, "reviewed")}
                        disabled={updatingId === item.id}
                        className="rounded bg-blue-600 px-3 py-1.5 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
                      >
                        Mark Reviewed
                      </button>
                      <button
                        onClick={() => handleUpdate(item.id, "dismissed")}
                        disabled={updatingId === item.id}
                        className="rounded bg-gray-200 px-3 py-1.5 text-sm text-gray-800 hover:bg-gray-300 disabled:opacity-50"
                      >
                        False Positive
                      </button>
                      <button
                        onClick={() => handleUpdate(item.id, "escalated")}
                        disabled={updatingId === item.id}
                        className="rounded bg-red-600 px-3 py-1.5 text-sm text-white hover:bg-red-700 disabled:opacity-50"
                      >
                        Needs Document Update
                      </button>
                    </div>
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

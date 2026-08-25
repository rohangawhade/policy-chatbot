import { useEffect, useState } from "react";
import { getDocumentHealth, type DocumentHealthItemDto } from "../../api/admin";
import { useEmployerStore } from "../../stores/employerStore";

function IssueBadges({ item }: { item: DocumentHealthItemDto }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {item.status === "failed" && (
        <span className="rounded-full bg-red-100 px-2.5 py-0.5 text-xs font-medium text-red-800">
          Failed ingestion
        </span>
      )}
      {item.is_stale && (
        <span className="rounded-full bg-yellow-100 px-2.5 py-0.5 text-xs font-medium text-yellow-800">
          Stale
        </span>
      )}
      {item.zero_query_hits && (
        <span className="rounded-full bg-gray-100 px-2.5 py-0.5 text-xs font-medium text-gray-700">
          Zero query hits
        </span>
      )}
    </div>
  );
}

export default function DocumentHealth() {
  const employers = useEmployerStore((state) => state.employers);
  const [documents, setDocuments] = useState<DocumentHealthItemDto[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      try {
        setDocuments(await getDocumentHealth());
        setError(null);
      } catch (err) {
        const message = err instanceof Error ? err.message : "Failed to load document health";
        setError(message);
      } finally {
        setLoading(false);
      }
    };

    load();
  }, []);

  const employerName = (id: string) => employers.find((e) => e.id === id)?.name ?? id;

  // "Table of documents with issues" (plan.md) -- a healthy document
  // (ready, fresh, queried at least once) has nothing to show here.
  const flagged = documents.filter(
    (doc) => doc.status === "failed" || doc.is_stale || doc.zero_query_hits,
  );

  if (loading) {
    return <div className="text-center text-gray-500">Loading document health...</div>;
  }

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-6">
      <h2 className="mb-4 text-lg font-semibold">Document Health</h2>

      {error && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 p-4 text-red-700">
          {error}
        </div>
      )}

      {flagged.length === 0 ? (
        <p className="text-center text-gray-500">No document issues found</p>
      ) : (
        <div className="space-y-2">
          {flagged.map((doc) => (
            <div key={doc.id} className="rounded-lg border border-gray-200 px-4 py-3">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="font-medium text-gray-900">{doc.title}</p>
                  <p className="text-sm text-gray-500">
                    {employerName(doc.employer_id)} · v{doc.version}
                  </p>
                </div>
                <IssueBadges item={doc} />
              </div>
              {doc.status === "failed" && doc.error_message && (
                <p className="mt-2 text-sm text-red-700">{doc.error_message}</p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

import { useEffect, useState } from "react";
import { deleteDocument, listDocuments } from "../../api/documents";
import { useDocumentStore } from "../../stores/documentStore";

function StatusBadge({ status }: { status: "processing" | "ready" | "failed" }) {
  const statusConfig = {
    processing: { bg: "bg-yellow-100", text: "text-yellow-800", label: "Processing" },
    ready: { bg: "bg-green-100", text: "text-green-800", label: "Ready" },
    failed: { bg: "bg-red-100", text: "text-red-800", label: "Failed" },
  };

  const config = statusConfig[status];
  return (
    <span className={`rounded-full px-3 py-1 text-sm font-medium ${config.bg} ${config.text}`}>
      {config.label}
    </span>
  );
}

export default function DocumentList() {
  const documents = useDocumentStore((state) => state.documents);
  const setDocuments = useDocumentStore((state) => state.setDocuments);
  const removeDocument = useDocumentStore((state) => state.removeDocument);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);

  useEffect(() => {
    const loadDocuments = async () => {
      try {
        // No employerId filter: EMPLOYER/EMPLOYEE accounts always see only
        // their own tenant regardless (backend derives it from the token);
        // an ADMIN account sees every tenant's documents.
        const docs = await listDocuments();
        setDocuments(
          docs.map((doc) => ({
            id: doc.id,
            employerId: doc.employer_id,
            title: doc.title,
            policyType: doc.policy_type,
            status: doc.status,
            version: doc.version,
          })),
        );
        setError(null);
      } catch (err) {
        const message = err instanceof Error ? err.message : "Failed to load documents";
        setError(message);
      } finally {
        setLoading(false);
      }
    };

    loadDocuments();
  }, [setDocuments]);

  const handleDelete = async (documentId: string) => {
    if (!confirm("Are you sure you want to delete this document?")) return;

    setDeleting(documentId);
    try {
      await deleteDocument(documentId);
      removeDocument(documentId);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Delete failed";
      setError(message);
    } finally {
      setDeleting(null);
    }
  };

  if (loading) {
    return (
      <div className="rounded-lg border border-gray-200 bg-white p-6">
        <h2 className="mb-4 text-lg font-semibold">Documents</h2>
        <div className="text-center text-gray-500">Loading documents...</div>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-6">
      <h2 className="mb-4 text-lg font-semibold">Documents</h2>

      {error && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 p-4 text-red-700">
          {error}
        </div>
      )}

      {documents.length === 0 ? (
        <div className="text-center text-gray-500">No documents uploaded yet</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-gray-200 text-left text-sm font-medium text-gray-600">
                <th className="pb-3">Title</th>
                <th className="pb-3">Status</th>
                <th className="pb-3">Version</th>
                <th className="pb-3">Actions</th>
              </tr>
            </thead>
            <tbody>
              {documents.map((doc) => (
                <tr key={doc.id} className="border-b border-gray-100">
                  <td className="py-4 pr-4">
                    <p className="max-w-xs font-medium text-gray-900">{doc.title}</p>
                  </td>
                  <td className="py-4 pr-4">
                    <StatusBadge status={doc.status} />
                  </td>
                  <td className="py-4 pr-4">v{doc.version}</td>
                  <td className="py-4 pr-4">
                    <button
                      onClick={() => handleDelete(doc.id)}
                      disabled={deleting === doc.id}
                      className="text-sm text-red-600 hover:text-red-800 disabled:opacity-50"
                    >
                      {deleting === doc.id ? "Deleting..." : "Delete"}
                    </button>
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

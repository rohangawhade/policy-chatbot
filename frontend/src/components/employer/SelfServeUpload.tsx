import { useEffect, useState } from "react";
import { deleteDocument, listDocuments, uploadDocument } from "../../api/documents";
import { useDocumentStore } from "../../stores/documentStore";

const SUPPORTED_FORMATS = ["pdf", "docx", "xlsx", "xml"];
const MAX_FILE_SIZE_MB = 25;

function titleFromFilename(filename: string): string {
  const withoutExtension = filename.replace(/\.[^./]+$/, "");
  return withoutExtension.trim() || filename;
}

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

// The employer-portal equivalent of admin's DocumentUpload + DocumentList
// (Step 10.4), but scoped to the caller's own employer only -- no
// employer-id field, since an EMPLOYER caller's uploads are always
// derived from their own token (document_routes.py's
// `_resolve_upload_employer_id`). plan.md's Step 10.8 file tree names
// this as one file, not the admin split's two.
export default function SelfServeUpload() {
  const documents = useDocumentStore((state) => state.documents);
  const setDocuments = useDocumentStore((state) => state.setDocuments);
  const removeDocument = useDocumentStore((state) => state.removeDocument);

  const [isDragOver, setIsDragOver] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<Record<string, number>>({});
  const [deleting, setDeleting] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const refreshDocuments = async () => {
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
  };

  useEffect(() => {
    refreshDocuments()
      .catch((err) => {
        const message = err instanceof Error ? err.message : "Failed to load documents";
        setError(message);
      })
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleFiles = async (files: FileList | null) => {
    if (!files) return;
    setError(null);

    for (const file of Array.from(files)) {
      const extension = file.name.split(".").pop()?.toLowerCase() || "";

      if (!SUPPORTED_FORMATS.includes(extension)) {
        setError(
          `Unsupported file format: ${extension}. Supported: ${SUPPORTED_FORMATS.join(", ")}`,
        );
        continue;
      }
      if (file.size > MAX_FILE_SIZE_MB * 1024 * 1024) {
        setError(`File too large: ${file.name} exceeds ${MAX_FILE_SIZE_MB}MB`);
        continue;
      }

      setIsUploading(true);
      setUploadProgress((prev) => ({ ...prev, [file.name]: 0 }));
      try {
        await uploadDocument(file, titleFromFilename(file.name));
        await refreshDocuments();
        setUploadProgress((prev) => ({ ...prev, [file.name]: 100 }));
      } catch (err) {
        const message = err instanceof Error ? err.message : "Upload failed";
        setError(message);
      } finally {
        setIsUploading(false);
      }
    }
  };

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

  return (
    <div className="space-y-6">
      <div className="rounded-lg border border-gray-200 bg-white p-6">
        <h2 className="mb-4 text-lg font-semibold">Upload Document</h2>
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setIsDragOver(true);
          }}
          onDragLeave={() => setIsDragOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setIsDragOver(false);
            handleFiles(e.dataTransfer.files);
          }}
          className={`rounded-lg border-2 border-dashed p-8 text-center transition ${
            isDragOver
              ? "border-blue-500 bg-blue-50"
              : "border-gray-300 bg-gray-50 hover:border-gray-400"
          }`}
        >
          <p className="mb-2 text-gray-600">Drag and drop files here</p>
          <label className="cursor-pointer text-blue-600 hover:underline">
            or click to select files
            <input
              type="file"
              multiple
              accept={SUPPORTED_FORMATS.map((fmt) => `.${fmt}`).join(",")}
              onChange={(e) => handleFiles(e.target.files)}
              className="hidden"
              disabled={isUploading}
            />
          </label>
          <p className="mt-2 text-sm text-gray-500">
            Supported: {SUPPORTED_FORMATS.join(", ")} (max {MAX_FILE_SIZE_MB}MB each)
          </p>
        </div>

        {error && (
          <div className="mt-4 rounded-lg border border-red-200 bg-red-50 p-4 text-red-700">
            {error}
          </div>
        )}

        {Object.entries(uploadProgress).length > 0 && (
          <div className="mt-4 space-y-2">
            {Object.entries(uploadProgress).map(([filename, progress]) => (
              <div key={filename}>
                <p className="text-sm font-medium text-gray-700">{filename}</p>
                <div className="h-2 w-full rounded-full bg-gray-200">
                  <div
                    className="h-full rounded-full bg-blue-500 transition-all duration-300"
                    style={{ width: `${progress}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="rounded-lg border border-gray-200 bg-white p-6">
        <h2 className="mb-4 text-lg font-semibold">Your Documents</h2>
        {loading ? (
          <div className="text-center text-gray-500">Loading documents...</div>
        ) : documents.length === 0 ? (
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
    </div>
  );
}

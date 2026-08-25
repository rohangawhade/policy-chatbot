import { useState } from "react";
import { listDocuments, uploadDocument } from "../../api/documents";
import { useDocumentStore } from "../../stores/documentStore";
import { useAuthStore } from "../../stores/authStore";

const SUPPORTED_FORMATS = ["pdf", "docx", "xlsx", "xml"];
const MAX_FILE_SIZE_MB = 25;

// title is required by POST /api/documents/upload and determines document
// identity (re-uploading the same title under the same employer bumps the
// version, backend/src/api/routes/document_routes.py) -- derived from the
// filename rather than a separate form field, so drag-and-drop of multiple
// files at once doesn't require naming each one individually.
function titleFromFilename(filename: string): string {
  const withoutExtension = filename.replace(/\.[^./]+$/, "");
  return withoutExtension.trim() || filename;
}

export default function DocumentUpload() {
  const [isDragOver, setIsDragOver] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<Record<string, number>>({});
  const [error, setError] = useState<string | null>(null);

  const setDocuments = useDocumentStore((state) => state.setDocuments);
  const role = useAuthStore((state) => state.role);
  const [adminEmployerId, setAdminEmployerId] = useState<string>("");

  const refreshDocuments = async () => {
    const docs = await listDocuments(role === "admin" ? adminEmployerId || undefined : undefined);
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

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragOver(true);
  };

  const handleDragLeave = () => {
    setIsDragOver(false);
  };

  const handleFiles = async (files: FileList | null) => {
    if (!files) return;

    setError(null);
    const filesToUpload = Array.from(files);

    for (const file of filesToUpload) {
      const extension = file.name.split(".").pop()?.toLowerCase() || "";

      // Validation
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

      // Upload
      setIsUploading(true);
      setUploadProgress((prev) => ({ ...prev, [file.name]: 0 }));

      try {
        await uploadDocument(file, titleFromFilename(file.name), {
          employerId: role === "admin" ? adminEmployerId : undefined,
        });
        // The upload response only carries id/status/version/error_message
        // (DocumentStatusResponseDto) -- refetch the full list rather than
        // merging a partial shape into the store.
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

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragOver(false);
    handleFiles(e.dataTransfer.files);
  };

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-6">
      <h2 className="mb-4 text-lg font-semibold">Upload Document</h2>

      {role === "admin" && (
        <div className="mb-4">
          <label className="block text-sm font-medium text-gray-700">Employer (Admin Only)</label>
          <input
            type="text"
            placeholder="Enter employer ID"
            value={adminEmployerId}
            onChange={(e) => setAdminEmployerId(e.target.value)}
            className="mt-1 w-full rounded border border-gray-300 px-3 py-2"
          />
        </div>
      )}

      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={`rounded-lg border-2 border-dashed p-8 text-center transition ${
          isDragOver
            ? "border-blue-500 bg-blue-50"
            : "border-gray-300 bg-gray-50 hover:border-gray-400"
        }`}
      >
        <svg
          className="mx-auto mb-4 h-12 w-12 text-gray-400"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
        </svg>
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
  );
}

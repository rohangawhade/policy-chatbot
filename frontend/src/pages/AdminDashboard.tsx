import { useState } from "react";
import DocumentList from "../components/admin/DocumentList";
import DocumentUpload from "../components/admin/DocumentUpload";
import EmployerManagement from "../components/admin/EmployerManagement";

type Tab = "management" | "documents" | "analytics";

export default function AdminDashboard() {
  const [activeTab, setActiveTab] = useState<Tab>("management");

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="mx-auto max-w-6xl px-4 py-8">
        <h1 className="mb-8 text-3xl font-bold text-gray-900">Admin Dashboard</h1>

        {/* Tab Navigation */}
        <div className="mb-6 border-b border-gray-200">
          <div className="flex gap-8">
            <button
              onClick={() => setActiveTab("management")}
              className={`px-4 py-3 font-medium transition ${
                activeTab === "management"
                  ? "border-b-2 border-blue-600 text-blue-600"
                  : "text-gray-600 hover:text-gray-900"
              }`}
            >
              Document & Employer Management
            </button>
            <button
              onClick={() => setActiveTab("documents")}
              className={`px-4 py-3 font-medium transition ${
                activeTab === "documents"
                  ? "border-b-2 border-blue-600 text-blue-600"
                  : "text-gray-600 hover:text-gray-900"
              }`}
            >
              Documents
            </button>
            <button
              onClick={() => setActiveTab("analytics")}
              className={`px-4 py-3 font-medium transition ${
                activeTab === "analytics"
                  ? "border-b-2 border-blue-600 text-blue-600"
                  : "text-gray-600 hover:text-gray-900"
              }`}
              disabled
            >
              Analytics (Coming Soon)
            </button>
          </div>
        </div>

        {/* Tab Content */}
        <div className="space-y-6">
          {activeTab === "management" && (
            <>
              <DocumentUpload />
              <EmployerManagement />
            </>
          )}

          {activeTab === "documents" && <DocumentList />}

          {activeTab === "analytics" && (
            <div className="rounded-lg border border-gray-200 bg-white p-6">
              <p className="text-gray-600">Analytics dashboard coming in Step 10.5</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

import { useState } from "react";
import AnalyticsDashboard from "../components/admin/AnalyticsDashboard";
import CostDashboard from "../components/admin/CostDashboard";
import DocumentHealth from "../components/admin/DocumentHealth";
import DocumentList from "../components/admin/DocumentList";
import DocumentUpload from "../components/admin/DocumentUpload";
import EmployerManagement from "../components/admin/EmployerManagement";
import FlaggedResponses from "../components/admin/FlaggedResponses";
import GuardrailsLog from "../components/admin/GuardrailsLog";
import LatencyMonitor from "../components/admin/LatencyMonitor";
import TopicHeatmap from "../components/admin/TopicHeatmap";
import UnansweredQueries from "../components/admin/UnansweredQueries";

type Tab = "management" | "documents" | "analytics" | "quality" | "operational";

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
            >
              Analytics
            </button>
            <button
              onClick={() => setActiveTab("quality")}
              className={`px-4 py-3 font-medium transition ${
                activeTab === "quality"
                  ? "border-b-2 border-blue-600 text-blue-600"
                  : "text-gray-600 hover:text-gray-900"
              }`}
            >
              Quality Monitoring
            </button>
            <button
              onClick={() => setActiveTab("operational")}
              className={`px-4 py-3 font-medium transition ${
                activeTab === "operational"
                  ? "border-b-2 border-blue-600 text-blue-600"
                  : "text-gray-600 hover:text-gray-900"
              }`}
            >
              Operational Health
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
            <div className="space-y-6">
              <AnalyticsDashboard />
              <CostDashboard />
            </div>
          )}

          {activeTab === "quality" && (
            <div className="space-y-6">
              <FlaggedResponses />
              <UnansweredQueries />
              <GuardrailsLog />
            </div>
          )}

          {activeTab === "operational" && (
            <div className="space-y-6">
              <LatencyMonitor />
              <DocumentHealth />
              <TopicHeatmap />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

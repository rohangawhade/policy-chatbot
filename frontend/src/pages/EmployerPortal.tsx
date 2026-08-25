import { useState } from "react";
import PolicyOverview from "../components/employer/PolicyOverview";
import SelfServeUpload from "../components/employer/SelfServeUpload";
import UserManagement from "../components/employer/UserManagement";

type Tab = "documents" | "employees" | "policies";

export default function EmployerPortal() {
  const [activeTab, setActiveTab] = useState<Tab>("documents");

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="mx-auto max-w-6xl px-4 py-8">
        <h1 className="mb-8 text-3xl font-bold text-gray-900">Employer Portal</h1>

        <div className="mb-6 border-b border-gray-200">
          <div className="flex gap-8">
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
              onClick={() => setActiveTab("employees")}
              className={`px-4 py-3 font-medium transition ${
                activeTab === "employees"
                  ? "border-b-2 border-blue-600 text-blue-600"
                  : "text-gray-600 hover:text-gray-900"
              }`}
            >
              Employees
            </button>
            <button
              onClick={() => setActiveTab("policies")}
              className={`px-4 py-3 font-medium transition ${
                activeTab === "policies"
                  ? "border-b-2 border-blue-600 text-blue-600"
                  : "text-gray-600 hover:text-gray-900"
              }`}
            >
              Policies
            </button>
          </div>
        </div>

        <div className="space-y-6">
          {activeTab === "documents" && <SelfServeUpload />}
          {activeTab === "employees" && <UserManagement />}
          {activeTab === "policies" && <PolicyOverview />}
        </div>
      </div>
    </div>
  );
}

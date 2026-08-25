import { useEffect, useState } from "react";
import { getOverview, type OverviewDto } from "../../api/admin";

interface StatCardProps {
  label: string;
  value: string;
}

function StatCard({ label, value }: StatCardProps) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-6">
      <p className="text-sm font-medium text-gray-600">{label}</p>
      <p className="mt-2 text-2xl font-semibold tabular-nums text-gray-900">{value}</p>
    </div>
  );
}

const currencyFormatter = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
});

export default function AnalyticsDashboard() {
  const [overview, setOverview] = useState<OverviewDto | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadOverview = async () => {
      try {
        setOverview(await getOverview());
        setError(null);
      } catch (err) {
        const message = err instanceof Error ? err.message : "Failed to load overview";
        setError(message);
      }
    };

    loadOverview();
  }, []);

  if (error) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-700">{error}</div>
    );
  }

  if (!overview) {
    return <div className="text-center text-gray-500">Loading overview...</div>;
  }

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <StatCard label="Queries today" value={overview.total_queries_today.toLocaleString()} />
      <StatCard label="Queries this week" value={overview.total_queries_week.toLocaleString()} />
      <StatCard
        label="Queries this month"
        value={overview.total_queries_month.toLocaleString()}
      />
      <StatCard label="Active users (7d)" value={overview.active_users_week.toLocaleString()} />
      <StatCard label="Documents indexed" value={overview.document_count.toLocaleString()} />
      <StatCard
        label="Avg. satisfaction"
        value={`${Math.round(overview.avg_satisfaction * 100)}%`}
      />
      <StatCard
        label="LLM cost this month"
        value={currencyFormatter.format(overview.cost_this_month_usd)}
      />
    </div>
  );
}

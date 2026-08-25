import { useEffect, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  getCostAlerts,
  getCostDashboard,
  type CostAlertDto,
  type CostDashboardDto,
} from "../../api/admin";
import { listEmployers } from "../../api/employers";
import { useEmployerStore } from "../../stores/employerStore";

const currencyFormatter = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
});

// Recharts renders one of these per data point via the Line's `dot` prop --
// alertDays (from GET /api/admin/cost-dashboard/alerts) is a same-shape,
// separately-fetched signal, since the line itself is an aggregate across
// (possibly) every employer while an alert is always employer+day-scoped;
// a day lights up red here if it contains at least one alert underneath it.
function ThresholdDot(alertDays: Set<string>) {
  return function Dot(props: { cx?: number; cy?: number; payload?: { date: string } }) {
    const { cx, cy, payload } = props;
    if (cx === undefined || cy === undefined || !payload) return null;
    const isAlert = alertDays.has(payload.date);
    return (
      <circle
        cx={cx}
        cy={cy}
        r={isAlert ? 5 : 3}
        fill={isAlert ? "#dc2626" : "#2563eb"}
        stroke="#fcfcfb"
        strokeWidth={1.5}
      />
    );
  };
}

export default function CostDashboard() {
  const employers = useEmployerStore((state) => state.employers);
  const setEmployers = useEmployerStore((state) => state.setEmployers);

  const [employerId, setEmployerId] = useState<string>("");
  const [start, setStart] = useState<string>("");
  const [end, setEnd] = useState<string>("");
  const [appliedFilters, setAppliedFilters] = useState<{
    employerId: string;
    start: string;
    end: string;
  }>({ employerId: "", start: "", end: "" });

  const [dashboard, setDashboard] = useState<CostDashboardDto | null>(null);
  const [alerts, setAlerts] = useState<CostAlertDto[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    listEmployers()
      .then((data) => setEmployers(data.map((e) => ({ id: e.id, name: e.name, isActive: e.is_active }))))
      .catch(() => {
        // Non-fatal: employer names are a display nicety -- the tables
        // below fall back to showing the raw employer_id if this fails.
      });
  }, [setEmployers]);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const params = {
          employerId: appliedFilters.employerId || undefined,
          start: appliedFilters.start || undefined,
          end: appliedFilters.end || undefined,
        };
        const [dashboardData, alertsData] = await Promise.all([
          getCostDashboard(params),
          getCostAlerts(params),
        ]);
        setDashboard(dashboardData);
        setAlerts(alertsData);
        setError(null);
      } catch (err) {
        const message = err instanceof Error ? err.message : "Failed to load cost dashboard";
        setError(message);
      } finally {
        setLoading(false);
      }
    };

    load();
  }, [appliedFilters]);

  const employerName = (id: string) => employers.find((e) => e.id === id)?.name ?? id;

  const handleApply = (e: React.FormEvent) => {
    e.preventDefault();
    setAppliedFilters({ employerId, start, end });
  };

  const alertDays = new Set(alerts.map((a) => a.date));
  const byModelSorted = dashboard
    ? [...dashboard.by_model].sort((a, b) => b.total_cost_usd - a.total_cost_usd)
    : [];
  const byEmployerSorted = dashboard
    ? [...dashboard.by_employer].sort((a, b) => b.total_cost_usd - a.total_cost_usd)
    : [];

  return (
    <div className="space-y-6">
      <form
        onSubmit={handleApply}
        className="flex flex-wrap items-end gap-3 rounded-lg border border-gray-200 bg-white p-4"
      >
        <div>
          <label className="block text-sm font-medium text-gray-700">Employer</label>
          <select
            value={employerId}
            onChange={(e) => setEmployerId(e.target.value)}
            className="mt-1 rounded border border-gray-300 px-3 py-2"
          >
            <option value="">All employers</option>
            {employers.map((employer) => (
              <option key={employer.id} value={employer.id}>
                {employer.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700">Start date</label>
          <input
            type="date"
            value={start}
            onChange={(e) => setStart(e.target.value)}
            className="mt-1 rounded border border-gray-300 px-3 py-2"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700">End date</label>
          <input
            type="date"
            value={end}
            onChange={(e) => setEnd(e.target.value)}
            className="mt-1 rounded border border-gray-300 px-3 py-2"
          />
        </div>
        <button
          type="submit"
          className="rounded bg-blue-600 px-4 py-2 text-white hover:bg-blue-700"
        >
          Apply
        </button>
      </form>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-700">{error}</div>
      )}

      {loading ? (
        <div className="text-center text-gray-500">Loading cost dashboard...</div>
      ) : (
        dashboard && (
          <>
            <div className="rounded-lg border border-gray-200 bg-white p-6">
              <div className="mb-4 flex items-baseline justify-between">
                <h2 className="text-lg font-semibold">Daily LLM spend</h2>
                <p className="text-2xl font-semibold tabular-nums text-gray-900">
                  {currencyFormatter.format(dashboard.total_cost_usd)}
                  <span className="ml-1 text-sm font-normal text-gray-500">total</span>
                </p>
              </div>
              {alertDays.size > 0 && (
                <p className="mb-3 text-sm text-red-600">
                  {alertDays.size} day{alertDays.size === 1 ? "" : "s"} exceeded the cost
                  threshold (highlighted in red below).
                </p>
              )}
              {dashboard.by_day.length === 0 ? (
                <div className="text-center text-gray-500">No spend recorded for this range</div>
              ) : (
                <ResponsiveContainer width="100%" height={280}>
                  <LineChart data={dashboard.by_day} margin={{ top: 8, right: 16, left: 8 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e1e0d9" vertical={false} />
                    <XAxis dataKey="date" tick={{ fontSize: 12, fill: "#898781" }} />
                    <YAxis
                      tick={{ fontSize: 12, fill: "#898781" }}
                      tickFormatter={(value: number) => currencyFormatter.format(value)}
                      width={80}
                    />
                    <Tooltip
                      formatter={(value?: number | string | readonly (number | string)[]) =>
                        currencyFormatter.format(Number(Array.isArray(value) ? value[0] : value))
                      }
                      labelStyle={{ color: "#0b0b0b" }}
                    />
                    <Line
                      type="monotone"
                      dataKey="total_cost_usd"
                      stroke="#2563eb"
                      strokeWidth={2}
                      dot={ThresholdDot(alertDays)}
                      activeDot={{ r: 6 }}
                    />
                  </LineChart>
                </ResponsiveContainer>
              )}
            </div>

            <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
              <div className="rounded-lg border border-gray-200 bg-white p-6">
                <h2 className="mb-4 text-lg font-semibold">By model tier</h2>
                {byModelSorted.length === 0 ? (
                  <p className="text-center text-gray-500">No data</p>
                ) : (
                  <table className="w-full">
                    <thead>
                      <tr className="border-b border-gray-200 text-left text-sm font-medium text-gray-600">
                        <th className="pb-2">Model</th>
                        <th className="pb-2">Calls</th>
                        <th className="pb-2">Cost</th>
                      </tr>
                    </thead>
                    <tbody>
                      {byModelSorted.map((row) => (
                        <tr key={row.model} className="border-b border-gray-100">
                          <td className="py-2 pr-4">{row.model}</td>
                          <td className="py-2 pr-4 tabular-nums">{row.call_count}</td>
                          <td className="py-2 tabular-nums">
                            {currencyFormatter.format(row.total_cost_usd)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>

              <div className="rounded-lg border border-gray-200 bg-white p-6">
                <h2 className="mb-4 text-lg font-semibold">By employer</h2>
                {byEmployerSorted.length === 0 ? (
                  <p className="text-center text-gray-500">No data</p>
                ) : (
                  <table className="w-full">
                    <thead>
                      <tr className="border-b border-gray-200 text-left text-sm font-medium text-gray-600">
                        <th className="pb-2">Employer</th>
                        <th className="pb-2">Cost</th>
                      </tr>
                    </thead>
                    <tbody>
                      {byEmployerSorted.map((row) => (
                        <tr key={row.employer_id} className="border-b border-gray-100">
                          <td className="py-2 pr-4">{employerName(row.employer_id)}</td>
                          <td className="py-2 tabular-nums">
                            {currencyFormatter.format(row.total_cost_usd)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </div>

            {alerts.length > 0 && (
              <div className="rounded-lg border border-red-200 bg-white p-6">
                <h2 className="mb-4 text-lg font-semibold text-red-700">
                  Days over the cost threshold
                </h2>
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-gray-200 text-left text-sm font-medium text-gray-600">
                      <th className="pb-2">Employer</th>
                      <th className="pb-2">Date</th>
                      <th className="pb-2">Spend</th>
                      <th className="pb-2">Threshold</th>
                    </tr>
                  </thead>
                  <tbody>
                    {alerts.map((alert) => (
                      <tr
                        key={`${alert.employer_id}-${alert.date}`}
                        className="border-b border-gray-100"
                      >
                        <td className="py-2 pr-4">{employerName(alert.employer_id)}</td>
                        <td className="py-2 pr-4">{alert.date}</td>
                        <td className="py-2 pr-4 tabular-nums text-red-600">
                          {currencyFormatter.format(alert.total_cost_usd)}
                        </td>
                        <td className="py-2 tabular-nums">
                          {currencyFormatter.format(alert.threshold_usd)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )
      )}
    </div>
  );
}

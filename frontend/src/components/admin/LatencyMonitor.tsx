import { useCallback, useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { getLatency, type LatencyResponseDto } from "../../api/admin";

const TIME_WINDOWS = {
  "1h": { label: "Last hour", ms: 60 * 60 * 1000 },
  "24h": { label: "Last 24h", ms: 24 * 60 * 60 * 1000 },
  "7d": { label: "Last 7d", ms: 7 * 24 * 60 * 60 * 1000 },
} as const;

type TimeWindow = keyof typeof TIME_WINDOWS;

// "real-time-ish (polling)" per plan.md -- there's no WebSocket/SSE port
// for this, so a periodic refetch while the tab is mounted is the
// pragmatic reading, same spirit as the chat UI's own SSE polling loop
// being the only other "live" surface in this app.
const POLL_INTERVAL_MS = 20_000;

export default function LatencyMonitor() {
  const [modelTier, setModelTier] = useState<string>("");
  const [timeWindow, setTimeWindow] = useState<TimeWindow>("24h");
  const [latency, setLatency] = useState<LatencyResponseDto | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const start = new Date(Date.now() - TIME_WINDOWS[timeWindow].ms).toISOString();
      const data = await getLatency({ modelTier: modelTier || undefined, start });
      setLatency(data);
      setError(null);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load latency stats";
      setError(message);
    } finally {
      setLoading(false);
    }
  }, [modelTier, timeWindow]);

  useEffect(() => {
    setLoading(true);
    load();
    const interval = setInterval(load, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [load]);

  const chartData = latency
    ? [
        { label: "Retrieval", p50: latency.retrieval.p50_ms, p95: latency.retrieval.p95_ms, p99: latency.retrieval.p99_ms },
        { label: "Generation", p50: latency.generation.p50_ms, p95: latency.generation.p95_ms, p99: latency.generation.p99_ms },
        { label: "Overall", p50: latency.overall.p50_ms, p95: latency.overall.p95_ms, p99: latency.overall.p99_ms },
      ]
    : [];

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-6">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-semibold">Latency Monitor</h2>
        <div className="flex gap-2">
          <select
            value={timeWindow}
            onChange={(e) => setTimeWindow(e.target.value as TimeWindow)}
            className="rounded border border-gray-300 px-3 py-1.5 text-sm"
          >
            {Object.entries(TIME_WINDOWS).map(([key, { label }]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
          <input
            type="text"
            placeholder="Filter by model tier"
            value={modelTier}
            onChange={(e) => setModelTier(e.target.value)}
            className="rounded border border-gray-300 px-3 py-1.5 text-sm"
          />
        </div>
      </div>

      {error && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 p-4 text-red-700">
          {error}
        </div>
      )}

      {loading ? (
        <div className="text-center text-gray-500">Loading latency stats...</div>
      ) : (
        latency && (
          <>
            <p className="mb-4 text-sm text-gray-500">
              {latency.overall.count} requests · retrieval vs. generation split, milliseconds
            </p>
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e1e0d9" vertical={false} />
                <XAxis dataKey="label" tick={{ fontSize: 12, fill: "#898781" }} />
                <YAxis tick={{ fontSize: 12, fill: "#898781" }} width={50} />
                <Tooltip />
                <Legend />
                <Bar dataKey="p50" name="p50" fill="#2a78d6" />
                <Bar dataKey="p95" name="p95" fill="#eb6834" />
                <Bar dataKey="p99" name="p99" fill="#e34948" />
              </BarChart>
            </ResponsiveContainer>

            {latency.by_model_tier.length > 0 && (
              <div className="mt-6 overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-gray-200 text-left text-sm font-medium text-gray-600">
                      <th className="pb-2">Model tier</th>
                      <th className="pb-2">Requests</th>
                      <th className="pb-2">p50</th>
                      <th className="pb-2">p95</th>
                      <th className="pb-2">p99</th>
                    </tr>
                  </thead>
                  <tbody>
                    {latency.by_model_tier.map((tier) => (
                      <tr key={tier.label} className="border-b border-gray-100">
                        <td className="py-2 pr-4">{tier.label}</td>
                        <td className="py-2 pr-4 tabular-nums">{tier.count}</td>
                        <td className="py-2 pr-4 tabular-nums">{tier.p50_ms.toFixed(0)}ms</td>
                        <td className="py-2 pr-4 tabular-nums">{tier.p95_ms.toFixed(0)}ms</td>
                        <td className="py-2 tabular-nums">{tier.p99_ms.toFixed(0)}ms</td>
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

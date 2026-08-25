import { useMemo, useState, useEffect } from "react";
import { getTopicHeatmap, type TopicHeatmapCellDto } from "../../api/admin";

const POLICY_TYPE_ROWS: { key: string; label: string }[] = [
  { key: "health", label: "Health" },
  { key: "dental", label: "Dental" },
  { key: "vision", label: "Vision" },
  { key: "life", label: "Life" },
  { key: "disability", label: "Disability" },
  { key: "unknown", label: "General / unknown" },
];

// Sequential single-hue ramp (blue, light -> dark), matching the same
// palette CostDashboard's chart already uses -- magnitude encoding gets
// one hue, never a rainbow.
const INTENSITY_STEPS = ["#f3f4f6", "#cde2fb", "#6da7ec", "#256abf", "#0d366b"];

function intensityColor(value: number, max: number): string {
  if (max === 0 || value === 0) return INTENSITY_STEPS[0];
  const ratio = value / max;
  const index = Math.min(INTENSITY_STEPS.length - 1, Math.ceil(ratio * (INTENSITY_STEPS.length - 1)));
  return INTENSITY_STEPS[Math.max(1, index)];
}

type Granularity = "week" | "month";

function bucketKey(dateStr: string, granularity: Granularity): string {
  const date = new Date(`${dateStr}T00:00:00Z`);
  if (granularity === "month") {
    return `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, "0")}`;
  }
  // Week bucket: the Monday of that ISO week, as YYYY-MM-DD.
  const day = date.getUTCDay();
  const diffToMonday = day === 0 ? -6 : 1 - day;
  const monday = new Date(date);
  monday.setUTCDate(date.getUTCDate() + diffToMonday);
  return monday.toISOString().slice(0, 10);
}

export default function TopicHeatmap() {
  const [cells, setCells] = useState<TopicHeatmapCellDto[]>([]);
  const [granularity, setGranularity] = useState<Granularity>("week");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      try {
        setCells(await getTopicHeatmap());
        setError(null);
      } catch (err) {
        const message = err instanceof Error ? err.message : "Failed to load topic heatmap";
        setError(message);
      } finally {
        setLoading(false);
      }
    };

    load();
  }, []);

  const { columns, grid, max } = useMemo(() => {
    const buckets = new Map<string, Map<string, number>>();
    let maxValue = 0;

    for (const cell of cells) {
      const bucket = bucketKey(cell.date, granularity);
      const policyKey = cell.policy_type ?? "unknown";
      if (!buckets.has(bucket)) buckets.set(bucket, new Map());
      const row = buckets.get(bucket)!;
      const total = (row.get(policyKey) ?? 0) + cell.query_count;
      row.set(policyKey, total);
      maxValue = Math.max(maxValue, total);
    }

    const sortedBuckets = Array.from(buckets.keys()).sort();
    return { columns: sortedBuckets, grid: buckets, max: maxValue };
  }, [cells, granularity]);

  if (loading) {
    return <div className="text-center text-gray-500">Loading topic heatmap...</div>;
  }

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-6">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-semibold">Topic Heatmap</h2>
        <select
          value={granularity}
          onChange={(e) => setGranularity(e.target.value as Granularity)}
          className="rounded border border-gray-300 px-3 py-1.5 text-sm"
        >
          <option value="week">By week</option>
          <option value="month">By month</option>
        </select>
      </div>
      <p className="mb-4 text-sm text-gray-500">
        Query volume by policy type — darker cells mean more queries.
      </p>

      {error && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 p-4 text-red-700">
          {error}
        </div>
      )}

      {columns.length === 0 ? (
        <p className="text-center text-gray-500">No query activity yet</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="border-separate border-spacing-1">
            <thead>
              <tr>
                <th className="pr-2 text-left text-xs font-medium text-gray-600">Policy type</th>
                {columns.map((col) => (
                  <th key={col} className="px-1 text-xs font-medium text-gray-600">
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {POLICY_TYPE_ROWS.map((row) => (
                <tr key={row.key}>
                  <td className="pr-2 text-sm text-gray-700 whitespace-nowrap">{row.label}</td>
                  {columns.map((col) => {
                    const value = grid.get(col)?.get(row.key) ?? 0;
                    return (
                      <td
                        key={col}
                        title={`${row.label}, ${col}: ${value} queries`}
                        className="h-8 w-8 rounded text-center text-xs"
                        style={{
                          backgroundColor: intensityColor(value, max),
                          color: value / (max || 1) > 0.6 ? "#ffffff" : "#0b0b0b",
                        }}
                      >
                        {value > 0 ? value : ""}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

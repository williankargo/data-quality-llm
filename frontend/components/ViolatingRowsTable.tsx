"use client";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface Props {
  rows: Record<string, unknown>[];
  violatingColumns: string[];
  truncated: boolean;
  totalCount: number;
  resultId: number;
}

export function ViolatingRowsTable({
  rows,
  violatingColumns,
  truncated,
  totalCount,
  resultId,
}: Props) {
  if (!rows.length) {
    return (
      <p className="text-xs text-gray-500 italic">
        This table has no primary key — row data unavailable.
      </p>
    );
  }

  const columns = Object.keys(rows[0]);
  const preview = rows.slice(0, 10);
  const downloadUrl = `${API_BASE}/results/${resultId}/violations.csv`;

  return (
    <div className="mt-2">
      <div className="flex justify-between items-center mb-1.5">
        <span className="text-xs text-gray-500">
          Showing {preview.length} of {totalCount} violating row
          {totalCount !== 1 ? "s" : ""}
          {truncated ? " (capped at 1,000)" : ""}
        </span>
        <a
          href={downloadUrl}
          download
          className="text-xs text-red-700 underline hover:text-red-900"
        >
          Download all violations (CSV)
        </a>
      </div>

      <div className="overflow-x-auto rounded border border-red-200">
        <table className="text-xs border-collapse w-full">
          <thead>
            <tr>
              {columns.map((col) => (
                <th
                  key={col}
                  className={`border-b border-red-200 px-2 py-1 text-left font-medium whitespace-nowrap ${
                    violatingColumns.includes(col)
                      ? "bg-red-200 text-red-900"
                      : "bg-gray-50 text-gray-700"
                  }`}
                >
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {preview.map((row, i) => (
              <tr key={i} className={i % 2 === 0 ? "bg-white" : "bg-gray-50"}>
                {columns.map((col) => (
                  <td
                    key={col}
                    className={`border-b border-gray-100 px-2 py-1 font-mono whitespace-nowrap ${
                      violatingColumns.includes(col) ? "bg-red-100 text-red-800" : "text-gray-800"
                    }`}
                  >
                    {row[col] === null ? (
                      <span className="text-gray-400 not-italic">null</span>
                    ) : (
                      String(row[col])
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

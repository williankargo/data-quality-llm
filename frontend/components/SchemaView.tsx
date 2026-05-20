"use client";
import { useTableSchema, useTableSample } from "@/lib/queries";
import { LoadingSkeleton } from "./LoadingSkeleton";
import { ErrorState } from "./ErrorState";
import { ApiError } from "@/lib/api";

interface SchemaViewProps {
  name: string;
}

export function SchemaView({ name }: SchemaViewProps) {
  const schemaQuery = useTableSchema(name);
  const sampleQuery = useTableSample(name);

  if (schemaQuery.isLoading) return <LoadingSkeleton lines={6} />;
  if (schemaQuery.error) {
    return (
      <ErrorState
        error={
          schemaQuery.error instanceof ApiError
            ? schemaQuery.error
            : new ApiError({
                code: "INTERNAL_ERROR",
                user_message: "Failed to load schema.",
                technical_detail: String(schemaQuery.error),
              })
        }
        onRetry={() => schemaQuery.refetch()}
      />
    );
  }

  const schema = schemaQuery.data!;
  const sample = sampleQuery.data;
  const columns = schema.columns;
  const displayColumns = columns.slice(0, 10);
  const rows = sample?.rows ?? [];

  return (
    <div className="space-y-6">
      {/* Column list */}
      <section>
        <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">
          Schema — {columns.length} columns · {schema.row_count.toLocaleString()} rows
        </h2>
        <div className="overflow-x-auto rounded-lg border">
          <table className="min-w-full text-sm">
            <thead className="bg-gray-50">
              <tr>
                {["Column", "Type", "Nullable", "Default"].map((h) => (
                  <th
                    key={h}
                    className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y">
              {columns.map((col) => (
                <tr key={col.name} className="bg-white hover:bg-gray-50">
                  <td className="px-4 py-2 font-mono font-medium text-gray-900">{col.name}</td>
                  <td className="px-4 py-2 text-gray-600">{col.data_type}</td>
                  <td className="px-4 py-2 text-gray-500">{col.is_nullable ? "YES" : "NO"}</td>
                  <td className="px-4 py-2 text-gray-500 font-mono text-xs">
                    {col.column_default ?? "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Sample data */}
      <section>
        <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">
          Sample Data — first {rows.length} rows
          {columns.length > 10 && " (showing first 10 columns)"}
        </h2>
        {sampleQuery.isLoading && <LoadingSkeleton lines={3} />}
        {sampleQuery.error && (
          <p className="text-sm text-red-500">Failed to load sample data.</p>
        )}
        {rows.length > 0 && (
          <div className="overflow-x-auto rounded-lg border">
            <table className="min-w-full text-sm">
              <thead className="bg-gray-50">
                <tr>
                  {displayColumns.map((col) => (
                    <th
                      key={col.name}
                      className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase whitespace-nowrap"
                    >
                      {col.name}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y">
                {rows.map((row, i) => (
                  <tr key={i} className="bg-white hover:bg-gray-50">
                    {displayColumns.map((col) => (
                      <td
                        key={col.name}
                        className="px-4 py-2 text-gray-700 font-mono text-xs whitespace-nowrap"
                      >
                        {row[col.name] === null ? (
                          <span className="text-gray-400 italic">null</span>
                        ) : (
                          String(row[col.name])
                        )}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

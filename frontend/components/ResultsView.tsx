"use client";
import { useRunSummaries, useRunDetail, useRules } from "@/lib/queries";
import { useTriggerRun } from "@/lib/mutations";
import { RunButton } from "./RunButton";
import { ResultRow } from "./ResultRow";
import { LoadingSkeleton } from "./LoadingSkeleton";
import { ErrorState } from "./ErrorState";
import { ApiError } from "@/lib/api";
import type { RunDetail } from "@/types/api";

interface ResultsViewProps {
  tableName: string;
}

function relativeTime(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diffMs / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs} hr${hrs !== 1 ? "s" : ""} ago`;
  const days = Math.floor(hrs / 24);
  return `${days} day${days !== 1 ? "s" : ""} ago`;
}

function RunHeader({ run }: { run: RunDetail }) {
  const parts: string[] = [];
  if (run.pass_count > 0) parts.push(`${run.pass_count} pass`);
  if (run.fail_count > 0) parts.push(`${run.fail_count} fail`);
  if (run.error_count > 0) parts.push(`${run.error_count} error`);

  return (
    <div className="text-sm text-gray-500">
      <span>Last run: {relativeTime(run.started_at)}</span>
      {parts.length > 0 && (
        <span className="ml-3 font-medium text-gray-700">{parts.join(" · ")}</span>
      )}
    </div>
  );
}

export function ResultsView({ tableName }: ResultsViewProps) {
  const summaries = useRunSummaries(tableName);
  const latestId = summaries.data?.[0]?.id;
  const detail = useRunDetail(latestId);
  const rulesQuery = useRules(tableName);
  const trigger = useTriggerRun(tableName);

  // Build rule_id → description lookup for plain-English result labels
  const descriptionMap = new Map<number, string>(
    (rulesQuery.data ?? []).map((r) => [r.id, r.description])
  );

  const isInitialLoading =
    summaries.isLoading || (latestId !== undefined && detail.isLoading);

  const run: RunDetail | undefined = detail.data;
  const queryError = summaries.error ?? detail.error;

  if (isInitialLoading) return <LoadingSkeleton lines={5} />;

  if (queryError && !run) {
    return (
      <ErrorState
        error={
          queryError instanceof ApiError
            ? queryError
            : new ApiError({
                code: "INTERNAL_ERROR",
                user_message: "Failed to load run history.",
                technical_detail: String(queryError),
              })
        }
        onRetry={() => summaries.refetch()}
      />
    );
  }

  return (
    <div className="space-y-5">
      {/* Header bar */}
      <div className="flex flex-wrap items-center gap-4">
        <RunButton onClick={() => trigger.mutate()} isLoading={trigger.isPending} />
        {run && <RunHeader run={run} />}
        {trigger.isError && (
          <p className="text-sm text-red-600">
            {trigger.error instanceof ApiError
              ? trigger.error.user_message
              : "Run failed. Please try again."}
          </p>
        )}
      </div>

      {/* Results list */}
      {!run ? (
        <div className="text-center py-16 text-gray-400">
          <p className="text-sm">No runs yet. Press &ldquo;Run checks&rdquo; to start.</p>
        </div>
      ) : run.results.length === 0 ? (
        <p className="text-sm text-gray-400">
          No rules to check. Add rules in the Rules tab first.
        </p>
      ) : (
        <div className="space-y-3">
          {run.results.map((result) => (
            <ResultRow
              key={result.id}
              result={result}
              description={
                result.rule_id !== null
                  ? (descriptionMap.get(result.rule_id) ?? null)
                  : null
              }
            />
          ))}
        </div>
      )}
    </div>
  );
}

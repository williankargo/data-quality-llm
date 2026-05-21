"use client";
import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useRunSummaries, useRunDetail, useRules } from "@/lib/queries";
import { useTriggerRun } from "@/lib/mutations";
import { RunButton } from "./RunButton";
import { ResultRow } from "./ResultRow";
import { RuleFilter } from "./RuleFilter";
import { LoadingSkeleton } from "./LoadingSkeleton";
import { ErrorState } from "./ErrorState";
import { ApiError } from "@/lib/api";
import type { RunDetail } from "@/types/api";

interface ResultsViewProps {
  tableName: string;
}

const SLOW_RUN_MS = 60_000;

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
  const queryClient = useQueryClient();

  // ID of the run triggered in this browser session (never cleared; updated on each new run)
  const [activeRunId, setActiveRunId] = useState<number | null>(null);
  const [runStartedAt, setRunStartedAt] = useState<number | null>(null);

  // Slow-warning: activated via setTimeout, reset by handleRun before a new run
  const [slowWarningActive, setSlowWarningActive] = useState(false);

  const summaries = useRunSummaries(tableName);
  const latestId = summaries.data?.[0]?.id ?? null;
  const rulesQuery = useRules(tableName);
  const trigger = useTriggerRun(tableName);

  // Prefer the actively-polled run; fall back to latest run from history
  const displayRunId = activeRunId ?? latestId;
  const detail = useRunDetail(displayRunId);

  const isRunning = detail.data?.status === "running";
  const prevStatusRef = useRef<string | undefined>(undefined);

  // Invalidate summaries when a polled run transitions from running → done
  useEffect(() => {
    const status = detail.data?.status;
    if (prevStatusRef.current === "running" && status !== "running" && status !== undefined) {
      queryClient.invalidateQueries({ queryKey: ["runs", tableName] });
    }
    prevStatusRef.current = status;
  }, [detail.data?.status, queryClient, tableName]);

  // Schedule slow-run warning; setState only inside the setTimeout callback (not in body)
  useEffect(() => {
    if (!isRunning || runStartedAt === null) return;
    const remaining = Math.max(0, SLOW_RUN_MS - (Date.now() - runStartedAt));
    const t = setTimeout(() => setSlowWarningActive(true), remaining);
    return () => clearTimeout(t);
  }, [isRunning, runStartedAt]);

  // showSlowWarning is derived so it auto-hides when isRunning becomes false
  const showSlowWarning = isRunning && slowWarningActive;

  const handleRun = (ruleIds?: number[]) => {
    setSlowWarningActive(false);
    trigger.mutate(ruleIds, {
      onSuccess: (data) => {
        setActiveRunId(data.id);
        setRunStartedAt(Date.now());
      },
    });
  };

  const descriptionMap = new Map<number, string>(
    (rulesQuery.data ?? []).map((r) => [r.id, r.description])
  );

  const isInitialLoading =
    summaries.isLoading || (displayRunId !== null && detail.isLoading && !detail.data);

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

  const isButtonDisabled = trigger.isPending || isRunning;

  return (
    <div className="space-y-4">
      {/* Header: Run button + status */}
      <div className="flex flex-wrap items-center gap-4">
        <RunButton onClick={() => handleRun()} isLoading={isButtonDisabled} />

        {isRunning && (
          <p className="text-sm text-indigo-600 animate-pulse">
            {rulesQuery.data != null
              ? `Running... ${run?.results.length ?? 0} / ${rulesQuery.data.length} rules`
              : `Running... ${run?.results.length ?? 0} rules completed`}
          </p>
        )}
        {run && !isRunning && <RunHeader run={run} />}

        {trigger.isError && !isRunning && (
          <p className="text-sm text-red-600">
            {trigger.error instanceof ApiError
              ? trigger.error.user_message
              : "Run failed. Please try again."}
          </p>
        )}
      </div>

      {/* Slow run warning */}
      {showSlowWarning && (
        <p className="text-sm text-amber-600 bg-amber-50 border border-amber-200 rounded px-3 py-2">
          Run is taking longer than expected — refresh to check later.
        </p>
      )}

      {/* Rule filter (collapsed by default, D#28) */}
      {rulesQuery.data && rulesQuery.data.length > 0 && (
        <RuleFilter
          rules={rulesQuery.data}
          onRunSelected={(ids) => handleRun(ids)}
          isLoading={isButtonDisabled}
        />
      )}

      {/* Running spinner when no results yet */}
      {isRunning && (!run || run.results.length === 0) && (
        <div className="flex flex-col items-center py-10 gap-3 text-indigo-400">
          <div className="w-6 h-6 border-2 border-indigo-400 border-t-transparent rounded-full animate-spin" />
          <p className="text-sm">
            {rulesQuery.data != null
              ? `Executing checks... 0 / ${rulesQuery.data.length} rules`
              : "Executing checks..."}
          </p>
        </div>
      )}

      {/* Results list */}
      {run && run.results.length > 0 && (
        <div className="space-y-3">
          {isRunning && (
            <p className="text-xs text-indigo-500">
              {rulesQuery.data != null
                ? `Run in progress — ${run.results.length} / ${rulesQuery.data.length} rules completed`
                : "Run in progress — results updating..."}
            </p>
          )}
          {run.results.map((result) => (
            <ResultRow
              key={result.id}
              result={result}
              description={
                result.rule_id !== null ? (descriptionMap.get(result.rule_id) ?? null) : null
              }
            />
          ))}
        </div>
      )}

      {/* Empty states */}
      {!run && !isRunning && (
        <div className="text-center py-16 text-gray-400">
          <p className="text-sm">No runs yet. Press &ldquo;Run checks&rdquo; to start.</p>
        </div>
      )}

      {run && run.results.length === 0 && !isRunning && (
        <p className="text-sm text-gray-400">
          No rules to check. Add rules in the Rules tab first.
        </p>
      )}
    </div>
  );
}

"use client";
import { useState } from "react";
import type { ExplainResponse, RunResult } from "@/types/api";
import { useExplainFailure } from "@/lib/mutations";
import { ResultExplainPanel } from "./ResultExplainPanel";

const STATUS_STYLES = {
  pass: {
    row: "border-green-200 bg-green-50",
    icon: "✅",
    badge: "text-green-700 bg-green-100",
    label: "Pass",
  },
  fail: {
    row: "border-red-200 bg-red-50",
    icon: "❌",
    badge: "text-red-700 bg-red-100",
    label: "Fail",
  },
  error: {
    row: "border-amber-200 bg-amber-50",
    icon: "⚠️",
    badge: "text-amber-700 bg-amber-100",
    label: "Error",
  },
} as const;

interface ResultRowProps {
  result: RunResult;
  description: string | null;
}

export function ResultRow({ result, description }: ResultRowProps) {
  const [expanded, setExpanded] = useState(false);
  const [explanation, setExplanation] = useState<ExplainResponse | null>(null);
  const style = STATUS_STYLES[result.status];
  const explainMutation = useExplainFailure();

  const hasSample =
    result.status === "fail" &&
    result.unexpected_sample &&
    result.unexpected_sample.length > 0;

  const sampleText = hasSample
    ? result.unexpected_sample!.map((v) => JSON.stringify(v)).join(", ")
    : null;

  function handleExplain() {
    explainMutation.mutate(result.id, {
      onSuccess: (data) => setExplanation(data),
    });
  }

  return (
    <div className={`border rounded-lg p-4 ${style.row}`}>
      <div className="flex items-start gap-3">
        <span className="text-lg leading-none mt-0.5">{style.icon}</span>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-gray-900">
            {description ?? result.expectation_type}
          </p>

          {result.status === "pass" && (
            <p className={`text-xs font-medium mt-1 ${STATUS_STYLES.pass.badge} inline-block px-1.5 py-0.5 rounded`}>
              {style.label}
            </p>
          )}

          {result.status === "fail" && (
            <div className="mt-1">
              <p className="text-sm text-red-700">
                {result.unexpected_count !== null
                  ? `${result.unexpected_count} violating row${result.unexpected_count !== 1 ? "s" : ""}.`
                  : "Violations found."}{" "}
                {sampleText && <>Sample: [{sampleText}]</>}
              </p>
              <button
                onClick={() => setExpanded((p) => !p)}
                className="text-xs text-red-600 underline mt-1 hover:text-red-800"
              >
                {expanded ? "▲ Hide details" : "▼ See details"}
              </button>

              {expanded && (
                <div className="mt-2">
                  {hasSample && (
                    <ul className="space-y-1 mb-3">
                      {result.unexpected_sample!.map((v, i) => (
                        <li
                          key={i}
                          className="text-xs font-mono text-red-700 bg-red-100 px-2 py-0.5 rounded"
                        >
                          {JSON.stringify(v)}
                        </li>
                      ))}
                    </ul>
                  )}

                  {explanation ? (
                    <ResultExplainPanel data={explanation} />
                  ) : (
                    <button
                      onClick={handleExplain}
                      disabled={explainMutation.isPending}
                      className="text-xs text-yellow-700 border border-yellow-400 bg-yellow-50 hover:bg-yellow-100 px-2 py-1 rounded disabled:opacity-50"
                    >
                      {explainMutation.isPending
                        ? "Analyzing…"
                        : "💡 Why did this fail?"}
                    </button>
                  )}

                  {explainMutation.isError && (
                    <p className="mt-1 text-xs text-red-600">
                      Could not load explanation. Please try again.
                    </p>
                  )}
                </div>
              )}
            </div>
          )}

          {result.status === "error" && (
            <div className="mt-1">
              <p className="text-sm text-amber-700">
                {result.error_message
                  ? `Error: ${result.error_message}`
                  : "Rule execution failed."}
              </p>
              <p className="text-xs text-amber-600 mt-0.5">
                Check the rule configuration.
              </p>
            </div>
          )}
        </div>

        <span
          className={`shrink-0 text-xs font-medium px-2 py-0.5 rounded-full ${style.badge}`}
        >
          {style.label}
        </span>
      </div>
    </div>
  );
}

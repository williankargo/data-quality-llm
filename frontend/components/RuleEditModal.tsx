"use client";
import { useEffect, useRef, useState } from "react";
import type { GeRule, RuleRecord, UpdateRuleRequest } from "@/types/api";
import { useUpdateRule } from "@/lib/mutations";
import { DiffLines } from "./DiffLines";
import { ApiError } from "@/lib/api";

interface RuleEditModalProps {
  rule: RuleRecord;
  tableName: string;
  onClose: () => void;
}

const COMMON_EXPECTATION_TYPES = [
  "expect_column_values_to_not_be_null",
  "expect_column_values_to_be_unique",
  "expect_column_values_to_be_between",
  "expect_column_values_to_be_in_set",
  "expect_column_values_to_not_be_in_set",
  "expect_column_values_to_match_regex",
  "expect_column_values_to_be_of_type",
  "expect_table_row_count_to_be_between",
  "expect_column_mean_to_be_between",
  "expect_column_min_to_be_between",
  "expect_column_max_to_be_between",
  "expect_column_sum_to_be_between",
];

export function RuleEditModal({ rule, tableName, onClose }: RuleEditModalProps) {
  const updateRule = useUpdateRule(tableName);
  const overlayRef = useRef<HTMLDivElement>(null);

  const [expectationType, setExpectationType] = useState(rule.expectation_type);
  const [kwargsJson, setKwargsJson] = useState(JSON.stringify(rule.kwargs, null, 2));
  const [description, setDescription] = useState(rule.description);
  const [jsonError, setJsonError] = useState<string | null>(null);

  const parseKwargs = (raw: string): Record<string, unknown> | null => {
    try {
      const parsed = JSON.parse(raw);
      if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
        return null;
      }
      return parsed as Record<string, unknown>;
    } catch {
      return null;
    }
  };

  const handleKwargsChange = (value: string) => {
    setKwargsJson(value);
    const parsed = parseKwargs(value);
    setJsonError(parsed === null ? "Invalid JSON — must be an object like { \"column\": \"name\" }" : null);
  };

  const editedRule: GeRule = {
    expectation_type: expectationType,
    kwargs: parseKwargs(kwargsJson) ?? rule.kwargs,
    description,
  };

  const hasChanges =
    expectationType !== rule.expectation_type ||
    JSON.stringify(parseKwargs(kwargsJson)) !== JSON.stringify(rule.kwargs) ||
    description !== rule.description;

  const handleSave = () => {
    const parsed = parseKwargs(kwargsJson);
    if (parsed === null) return;
    const body: UpdateRuleRequest = { expectation_type: expectationType, kwargs: parsed, description };
    updateRule.mutate({ id: rule.id, body }, { onSuccess: onClose });
  };

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [onClose]);

  const handleOverlayClick = (e: React.MouseEvent) => {
    if (e.target === overlayRef.current) onClose();
  };

  return (
    <div
      ref={overlayRef}
      onClick={handleOverlayClick}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
    >
      <div className="bg-white rounded-xl shadow-xl w-full max-w-4xl max-h-[90vh] flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b">
          <h2 className="text-base font-semibold text-gray-900">Edit Rule</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 transition-colors text-xl leading-none"
            aria-label="Close"
          >
            &times;
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
          <div className="grid grid-cols-2 gap-4">
            {/* Left: original */}
            <div>
              <p className="text-xs font-medium text-gray-500 mb-1">Original</p>
              <pre className="bg-gray-50 border rounded-lg p-3 text-xs font-mono text-gray-700 overflow-x-auto whitespace-pre-wrap break-all">
                {JSON.stringify({ expectation_type: rule.expectation_type, kwargs: rule.kwargs, description: rule.description }, null, 2)}
              </pre>
            </div>

            {/* Right: editable */}
            <div className="space-y-3">
              <p className="text-xs font-medium text-gray-500 mb-1">Edit</p>

              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">
                  Expectation Type
                </label>
                <select
                  value={expectationType}
                  onChange={(e) => setExpectationType(e.target.value)}
                  className="w-full text-xs text-gray-900 border rounded-md px-2 py-1.5 bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  {COMMON_EXPECTATION_TYPES.includes(expectationType) ? null : (
                    <option value={expectationType}>{expectationType}</option>
                  )}
                  {COMMON_EXPECTATION_TYPES.map((t) => (
                    <option key={t} value={t}>{t}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">
                  kwargs (JSON)
                </label>
                <textarea
                  value={kwargsJson}
                  onChange={(e) => handleKwargsChange(e.target.value)}
                  rows={5}
                  className={`w-full text-xs text-gray-900 font-mono border rounded-md px-2 py-1.5 resize-y focus:outline-none focus:ring-2 focus:ring-blue-500 ${
                    jsonError ? "border-red-400 bg-red-50" : ""
                  }`}
                />
                {jsonError && (
                  <p className="text-xs text-red-600 mt-1">{jsonError}</p>
                )}
              </div>

              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">
                  Description
                </label>
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  rows={2}
                  className="w-full text-xs text-gray-900 border rounded-md px-2 py-1.5 resize-y focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
            </div>
          </div>

          {/* Diff view */}
          <div>
            <p className="text-xs font-medium text-gray-500 mb-2">Changes</p>
            <DiffLines original={rule} edited={editedRule} />
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-6 py-4 border-t bg-gray-50">
          <div>
            {updateRule.isError && (
              <p className="text-xs text-red-600">
                {updateRule.error instanceof ApiError
                  ? updateRule.error.user_message
                  : "Failed to save changes."}
              </p>
            )}
          </div>
          <div className="flex gap-2">
            <button
              onClick={onClose}
              className="px-4 py-1.5 text-sm font-medium text-gray-700 border rounded-md hover:bg-gray-100 transition-colors"
            >
              Discard
            </button>
            <button
              onClick={handleSave}
              disabled={!!jsonError || !hasChanges || updateRule.isPending}
              className="px-4 py-1.5 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {updateRule.isPending ? "Saving..." : "Save"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

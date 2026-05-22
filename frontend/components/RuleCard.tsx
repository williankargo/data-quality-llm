"use client";
import { useState } from "react";
import { FrontendDraft, RuleRecord, CreateRuleRequest } from "@/types/api";
import { useSaveRule, useDeleteRule } from "@/lib/mutations";
import { ApiError } from "@/lib/api";
import { RuleEditModal } from "./RuleEditModal";

interface DraftProps {
  mode: "draft";
  draft: FrontendDraft;
  tableName: string;
  onDiscard: () => void;
}

interface SavedProps {
  mode: "saved";
  rule: RuleRecord;
  tableName: string;
}

type RuleCardProps = DraftProps | SavedProps;

const SOURCE_LABELS: Record<string, string> = {
  ai_schema: "AI suggested",
  ai_nl: "AI from description",
  user: "Manual",
};

export function RuleCard(props: RuleCardProps) {
  const { tableName } = props;
  const saveRule = useSaveRule(tableName);
  const deleteRule = useDeleteRule(tableName);

  if (props.mode === "draft") {
    const { draft, onDiscard } = props;

    const handleSave = () => {
      const req: CreateRuleRequest = {
        expectation_type: draft.expectation_type,
        kwargs: draft.kwargs,
        description: draft.description,
        table_name: tableName,
        source: draft.source,
      };
      saveRule.mutate(req, { onSuccess: onDiscard });
    };

    return (
      <div className="border rounded-lg p-4 bg-white shadow-sm">
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <p className="text-xs font-mono text-gray-400 truncate">{draft.expectation_type}</p>
            <p className="text-sm text-gray-900 mt-1">{draft.description}</p>
          </div>
          {draft.already_saved && (
            <span className="shrink-0 text-xs font-medium text-green-700 bg-green-100 px-2 py-0.5 rounded-full whitespace-nowrap">
              Already saved
            </span>
          )}
        </div>
        <div className="flex items-center justify-end gap-2 mt-3">
          <button
            onClick={onDiscard}
            className="px-3 py-1.5 text-xs font-medium text-gray-600 border rounded hover:bg-gray-50 transition-colors"
          >
            Discard
          </button>
          <button
            onClick={handleSave}
            disabled={draft.already_saved || saveRule.isPending}
            className="px-3 py-1.5 text-xs font-medium text-white bg-blue-600 rounded hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {saveRule.isPending ? "Saving..." : "Save"}
          </button>
        </div>
        {saveRule.isError && (
          <p className="text-xs text-red-600 mt-2">
            {saveRule.error instanceof ApiError
              ? saveRule.error.user_message
              : "Failed to save rule."}
          </p>
        )}
      </div>
    );
  }

  // Saved mode
  const { rule } = props;
  const [editing, setEditing] = useState(false);
  return (
    <>
      <div className="border rounded-lg p-4 bg-white shadow-sm">
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <p className="text-xs font-mono text-gray-400 truncate">{rule.expectation_type}</p>
            <p className="text-sm text-gray-900 mt-1">{rule.description}</p>
            <p className="text-xs text-gray-400 mt-1">{SOURCE_LABELS[rule.source] ?? rule.source}</p>
          </div>
          <div className="flex shrink-0 gap-2">
            <button
              onClick={() => setEditing(true)}
              className="px-3 py-1.5 text-xs font-medium text-blue-600 border border-blue-200 rounded hover:bg-blue-50 transition-colors"
            >
              Edit
            </button>
            <button
              onClick={() => deleteRule.mutate(rule.id)}
              disabled={deleteRule.isPending}
              className="px-3 py-1.5 text-xs font-medium text-red-600 border border-red-200 rounded hover:bg-red-50 disabled:opacity-50 transition-colors"
            >
              Delete
            </button>
          </div>
        </div>
      </div>
      {editing && (
        <RuleEditModal
          rule={rule}
          tableName={tableName}
          onClose={() => setEditing(false)}
        />
      )}
    </>
  );
}

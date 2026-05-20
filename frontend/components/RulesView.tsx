"use client";
import { useState } from "react";
import { useRules } from "@/lib/queries";
import { useSuggestRules } from "@/lib/mutations";
import { RuleCard } from "./RuleCard";
import { NlRuleInput } from "./NlRuleInput";
import { LoadingSkeleton } from "./LoadingSkeleton";
import { ErrorState } from "./ErrorState";
import { ApiError } from "@/lib/api";
import type { FrontendDraft } from "@/types/api";

interface RulesViewProps {
  tableName: string;
}

export function RulesView({ tableName }: RulesViewProps) {
  const [drafts, setDrafts] = useState<FrontendDraft[]>([]);
  const rulesQuery = useRules(tableName);
  const suggest = useSuggestRules(tableName);

  const handleSuggest = () => {
    suggest.mutate(undefined, {
      onSuccess: (data) => {
        const withSource: FrontendDraft[] = data.drafts.map((d) => ({
          ...d,
          source: "ai_schema" as const,
        }));
        setDrafts(withSource);
      },
    });
  };

  const discardDraft = (index: number) => {
    setDrafts((prev) => prev.filter((_, i) => i !== index));
  };

  const addNlDraft = (draft: FrontendDraft) => {
    setDrafts((prev) => [draft, ...prev]);
  };

  if (rulesQuery.isLoading) return <LoadingSkeleton lines={4} />;
  if (rulesQuery.error) {
    return (
      <ErrorState
        error={
          rulesQuery.error instanceof ApiError
            ? rulesQuery.error
            : new ApiError({
                code: "INTERNAL_ERROR",
                user_message: "Failed to load rules.",
                technical_detail: String(rulesQuery.error),
              })
        }
        onRetry={() => rulesQuery.refetch()}
      />
    );
  }

  const savedRules = rulesQuery.data ?? [];

  return (
    <div className="space-y-6">
      {/* Action bar */}
      <div className="flex flex-wrap items-start gap-3">
        <button
          onClick={handleSuggest}
          disabled={suggest.isPending}
          className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 disabled:opacity-50 transition-colors"
        >
          {suggest.isPending ? "Suggesting..." : "✨ Suggest rules"}
        </button>
        <NlRuleInput tableName={tableName} onRuleGenerated={addNlDraft} />
        {suggest.isError && (
          <p className="text-sm text-red-600 self-center">
            {suggest.error instanceof ApiError
              ? suggest.error.user_message
              : "Failed to get suggestions."}
          </p>
        )}
      </div>

      {/* Draft cards */}
      {drafts.length > 0 && (
        <section>
          <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">
            Suggested ({drafts.length})
          </h2>
          <div className="space-y-3">
            {drafts.map((draft, i) => (
              <RuleCard
                key={i}
                mode="draft"
                draft={draft}
                tableName={tableName}
                onDiscard={() => discardDraft(i)}
              />
            ))}
          </div>
        </section>
      )}

      {/* Saved rules */}
      <section>
        <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">
          Saved rules ({savedRules.length})
        </h2>
        {savedRules.length === 0 ? (
          <p className="text-sm text-gray-400">
            No rules saved yet. Use &ldquo;Suggest rules&rdquo; or &ldquo;Add rule by description&rdquo; to get started.
          </p>
        ) : (
          <div className="space-y-3">
            {savedRules.map((rule) => (
              <RuleCard key={rule.id} mode="saved" rule={rule} tableName={tableName} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

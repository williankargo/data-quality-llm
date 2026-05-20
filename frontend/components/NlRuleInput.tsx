"use client";
import { useState } from "react";
import { useNlRule } from "@/lib/mutations";
import { FrontendDraft } from "@/types/api";
import { ApiError } from "@/lib/api";

interface NlRuleInputProps {
  tableName: string;
  onRuleGenerated: (draft: FrontendDraft) => void;
}

export function NlRuleInput({ tableName, onRuleGenerated }: NlRuleInputProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [description, setDescription] = useState("");
  const [clarification, setClarification] = useState<string | null>(null);
  const nlRule = useNlRule(tableName);

  const close = () => {
    setIsOpen(false);
    setClarification(null);
    setDescription("");
    nlRule.reset();
  };

  const handleSubmit = () => {
    if (!description.trim()) return;
    setClarification(null);
    nlRule.mutate(description, {
      onSuccess: (result) => {
        if (result.type === "clarification") {
          setClarification(result.question);
          setDescription("");
        } else {
          onRuleGenerated({
            ...result.rule,
            already_saved: false,
            source: "ai_nl",
          });
          close();
        }
      },
    });
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      handleSubmit();
    }
  };

  if (!isOpen) {
    return (
      <button
        onClick={() => setIsOpen(true)}
        className="px-3 py-2 text-sm font-medium text-gray-700 border rounded-md hover:bg-gray-50 transition-colors"
      >
        Add rule by description
      </button>
    );
  }

  return (
    <div className="w-full border rounded-lg p-4 bg-white shadow-sm">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-medium text-gray-900">Describe a rule in plain English</h3>
        <button
          onClick={close}
          aria-label="Close"
          className="text-gray-400 hover:text-gray-600 text-xl leading-none"
        >
          &times;
        </button>
      </div>

      {clarification && (
        <div className="mb-3 p-3 bg-amber-50 border border-amber-200 rounded-md">
          <p className="text-sm text-amber-800 font-medium mb-0.5">Need more detail:</p>
          <p className="text-sm text-amber-700">{clarification}</p>
        </div>
      )}

      <textarea
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="e.g. premium must be greater than 0"
        rows={3}
        className="w-full text-sm border rounded-md px-3 py-2 resize-none focus:outline-none focus:ring-2 focus:ring-blue-500"
      />
      <p className="text-xs text-gray-400 mt-1">Press Cmd+Enter to submit</p>

      <div className="flex gap-2 mt-2 justify-end">
        <button
          onClick={close}
          className="px-3 py-1.5 text-xs font-medium text-gray-600 border rounded hover:bg-gray-50 transition-colors"
        >
          Cancel
        </button>
        <button
          onClick={handleSubmit}
          disabled={!description.trim() || nlRule.isPending}
          className="px-3 py-1.5 text-xs font-medium text-white bg-blue-600 rounded hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {nlRule.isPending ? "Thinking..." : "Submit"}
        </button>
      </div>

      {nlRule.isError && (
        <p className="text-xs text-red-600 mt-2">
          {nlRule.error instanceof ApiError
            ? nlRule.error.user_message
            : "Failed to generate rule."}
        </p>
      )}
    </div>
  );
}

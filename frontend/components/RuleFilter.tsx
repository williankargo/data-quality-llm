"use client";
import { useState } from "react";
import type { RuleRecord } from "@/types/api";

interface RuleFilterProps {
  rules: RuleRecord[];
  onRunSelected: (ruleIds: number[]) => void;
  isLoading: boolean;
}

export function RuleFilter({ rules, onRunSelected, isLoading }: RuleFilterProps) {
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<Set<number>>(new Set());

  const handleOpen = () => {
    setSelected(new Set(rules.map((r) => r.id)));
    setOpen(true);
  };

  const toggle = (id: number, checked: boolean) => {
    const next = new Set(selected);
    if (checked) next.add(id);
    else next.delete(id);
    setSelected(next);
  };

  if (!open) {
    return (
      <button
        onClick={handleOpen}
        className="text-xs text-gray-400 underline hover:text-gray-600"
      >
        Filter rules to run
      </button>
    );
  }

  return (
    <div className="border border-gray-200 rounded-md p-3 bg-gray-50 space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-gray-600">Select rules to run</span>
        <button
          onClick={() => setOpen(false)}
          className="text-xs text-gray-400 hover:text-gray-600"
          aria-label="Close filter"
        >
          ✕
        </button>
      </div>

      <div className="space-y-1 max-h-48 overflow-y-auto">
        {rules.map((rule) => (
          <label key={rule.id} className="flex items-center gap-2 text-sm cursor-pointer">
            <input
              type="checkbox"
              checked={selected.has(rule.id)}
              onChange={(e) => toggle(rule.id, e.target.checked)}
              className="accent-indigo-600"
            />
            <span className="text-gray-700 truncate">
              {rule.description || rule.expectation_type}
            </span>
          </label>
        ))}
      </div>

      <div className="flex items-center gap-2 pt-1">
        <button
          onClick={() => onRunSelected(Array.from(selected))}
          disabled={selected.size === 0 || isLoading}
          className="px-3 py-1 text-xs font-medium text-white bg-indigo-600 rounded hover:bg-indigo-700 disabled:opacity-50 transition-colors"
        >
          Run selected ({selected.size})
        </button>
        <button
          onClick={() => setSelected(new Set(rules.map((r) => r.id)))}
          className="text-xs text-gray-500 hover:text-gray-700 underline"
        >
          Select all
        </button>
        <button
          onClick={() => setSelected(new Set())}
          className="text-xs text-gray-500 hover:text-gray-700 underline"
        >
          Clear
        </button>
      </div>
    </div>
  );
}

"use client";
import { useState } from "react";
import { NlChatThread } from "./NlChatThread";
import type { FrontendDraft } from "@/types/api";

interface NlRuleInputProps {
  tableName: string;
  onRuleGenerated: (draft: FrontendDraft) => void;
}

export function NlRuleInput({ tableName, onRuleGenerated }: NlRuleInputProps) {
  const [isOpen, setIsOpen] = useState(false);

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
    <NlChatThread
      tableName={tableName}
      onRuleGenerated={onRuleGenerated}
      onClose={() => setIsOpen(false)}
    />
  );
}

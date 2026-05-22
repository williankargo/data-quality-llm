"use client";
import { useEffect, useRef, useState } from "react";
import { useNlRule } from "@/lib/mutations";
import { ApiError } from "@/lib/api";
import type { ChatMessage, FrontendDraft, NlRuleResponse } from "@/types/api";

interface NlChatThreadProps {
  tableName: string;
  onRuleGenerated: (draft: FrontendDraft) => void;
  onClose: () => void;
}

const MAX_USER_TURNS = 5;

function serializeResponse(result: NlRuleResponse): string {
  if (result.type === "rule") {
    return JSON.stringify({ type: "rule", rule: result.rule });
  }
  return JSON.stringify({ type: "clarification", question: result.question });
}

function parseAssistantContent(content: string): NlRuleResponse | null {
  try {
    return JSON.parse(content) as NlRuleResponse;
  } catch {
    return null;
  }
}

export function NlChatThread({
  tableName,
  onRuleGenerated,
  onClose,
}: NlChatThreadProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [lastRule, setLastRule] = useState<FrontendDraft | null>(null);
  const nlRule = useNlRule(tableName);
  const bottomRef = useRef<HTMLDivElement>(null);

  const userTurns = messages.filter((m) => m.role === "user").length;
  const isCapped = userTurns >= MAX_USER_TURNS;

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, nlRule.isPending]);

  const reset = () => {
    setMessages([]);
    setDraft("");
    setLastRule(null);
    nlRule.reset();
  };

  const handleSubmit = () => {
    if (!draft.trim() || nlRule.isPending || isCapped) return;

    const userMsg: ChatMessage = { role: "user", content: draft.trim() };
    const newMessages = [...messages, userMsg];
    setMessages(newMessages);
    setDraft("");

    nlRule.mutate(newMessages, {
      onSuccess: (result) => {
        const assistantMsg: ChatMessage = {
          role: "assistant",
          content: serializeResponse(result),
        };
        setMessages((prev) => [...prev, assistantMsg]);
        if (result.type === "rule") {
          setLastRule({ ...result.rule, already_saved: false, source: "ai_nl" });
        } else {
          setLastRule(null);
        }
      },
      onError: () => {
        // Roll back the optimistically appended user message.
        setMessages((prev) => prev.slice(0, -1));
      },
    });
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      handleSubmit();
    }
  };

  const handleSave = () => {
    if (lastRule) {
      onRuleGenerated(lastRule);
      onClose();
    }
  };

  return (
    <div className="w-full border rounded-lg p-4 bg-white shadow-sm">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-medium text-gray-900">
          Describe a rule in plain English
        </h3>
        <div className="flex items-center gap-3">
          {messages.length > 0 && (
            <button
              onClick={reset}
              className="text-xs text-gray-500 hover:text-gray-700 underline"
            >
              Start over
            </button>
          )}
          <button
            onClick={onClose}
            aria-label="Close"
            className="text-gray-400 hover:text-gray-600 text-xl leading-none"
          >
            &times;
          </button>
        </div>
      </div>

      {/* Message thread */}
      {messages.length > 0 && (
        <div className="mb-3 space-y-2 max-h-72 overflow-y-auto pr-1">
          {messages.map((msg, i) => {
            if (msg.role === "user") {
              return (
                <div key={i} className="flex justify-end">
                  <div className="bg-blue-600 text-white text-sm rounded-lg px-3 py-2 max-w-xs break-words">
                    {msg.content}
                  </div>
                </div>
              );
            }
            const parsed = parseAssistantContent(msg.content);
            if (!parsed) return null;
            const isLatestAssistant = i === messages.length - 1;

            if (parsed.type === "rule") {
              return (
                <div key={i} className="flex justify-start">
                  <div className="bg-gray-100 text-gray-900 text-sm rounded-lg px-3 py-2 max-w-sm">
                    <p className="font-medium mb-0.5">{parsed.rule.description}</p>
                    <p className="text-xs text-gray-500 font-mono">
                      {parsed.rule.expectation_type}
                    </p>
                    {isLatestAssistant && (
                      <button
                        onClick={handleSave}
                        className="mt-2 text-xs font-medium text-blue-600 hover:underline"
                      >
                        Save this rule &rarr;
                      </button>
                    )}
                  </div>
                </div>
              );
            }

            return (
              <div key={i} className="flex justify-start">
                <div className="bg-amber-50 border border-amber-200 text-sm rounded-lg px-3 py-2 max-w-sm">
                  <p className="text-xs font-medium text-amber-700 mb-0.5">
                    Need more detail:
                  </p>
                  <p className="text-amber-800">{parsed.question}</p>
                </div>
              </div>
            );
          })}

          {nlRule.isPending && (
            <div className="flex justify-start">
              <div className="bg-gray-100 text-gray-400 text-sm rounded-lg px-3 py-2">
                Thinking...
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>
      )}

      {/* Cap warning */}
      {isCapped && (
        <div className="mb-3 p-2 bg-amber-50 border border-amber-200 rounded text-xs text-amber-800">
          Conversation too long —{" "}
          <button onClick={reset} className="underline font-medium">
            start over
          </button>{" "}
          to describe a new rule.
        </div>
      )}

      {/* Input area */}
      {!isCapped && (
        <>
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              messages.length === 0
                ? "e.g. premium must be greater than 0"
                : "Refine or add another constraint..."
            }
            rows={2}
            disabled={nlRule.isPending}
            className="w-full text-sm text-gray-900 border rounded-md px-3 py-2 resize-none focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
          />
          <p className="text-xs text-gray-400 mt-0.5">Press Cmd+Enter to submit</p>
          <div className="flex justify-end mt-2">
            <button
              onClick={handleSubmit}
              disabled={!draft.trim() || nlRule.isPending}
              className="px-3 py-1.5 text-xs font-medium text-white bg-blue-600 rounded hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {nlRule.isPending ? "Thinking..." : "Submit"}
            </button>
          </div>
        </>
      )}

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

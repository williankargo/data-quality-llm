"use client";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "./api";
import type {
  ChatMessage,
  CreateRuleRequest,
  ExplainResponse,
  NlRuleResponse,
  RuleRecord,
  RunDetail,
  RunSummary,
  SuggestResponse,
  UpdateRuleRequest,
} from "../types/api";

export const useSuggestRules = (tableName: string) => {
  return useMutation({
    mutationFn: () =>
      apiFetch<SuggestResponse>("/rules/suggest", {
        method: "POST",
        body: { table_name: tableName },
      }),
  });
};

export const useSaveRule = (tableName: string) => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (rule: CreateRuleRequest) =>
      apiFetch<RuleRecord>("/rules", { method: "POST", body: rule }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["rules", tableName] });
    },
  });
};

export const useDeleteRule = (tableName: string) => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => apiFetch(`/rules/${id}`, { method: "DELETE" }),
    onMutate: async (id) => {
      await queryClient.cancelQueries({ queryKey: ["rules", tableName] });
      const prev = queryClient.getQueryData<RuleRecord[]>(["rules", tableName]);
      queryClient.setQueryData<RuleRecord[]>(["rules", tableName], (old) =>
        old?.filter((r) => r.id !== id) ?? []
      );
      return { prev };
    },
    onError: (_e, _id, ctx) => {
      if (ctx?.prev) {
        queryClient.setQueryData(["rules", tableName], ctx.prev);
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["rules", tableName] });
    },
  });
};

export const useNlRule = (tableName: string) => {
  return useMutation({
    mutationFn: (messages: ChatMessage[]) =>
      apiFetch<NlRuleResponse>("/rules/from-nl", {
        method: "POST",
        body: { table_name: tableName, messages },
      }),
  });
};

export const useUpdateRule = (tableName: string) => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: UpdateRuleRequest }) =>
      apiFetch<RuleRecord>(`/rules/${id}`, { method: "PUT", body }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["rules", tableName] });
    },
  });
};

export const useExplainFailure = () => {
  return useMutation({
    mutationFn: (resultId: number) =>
      apiFetch<ExplainResponse>(`/results/${resultId}/explain`, {
        method: "POST",
        body: {},
      }),
  });
};

export const useTriggerRun = (tableName: string) => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (ruleIds?: number[]) =>
      apiFetch<RunSummary>("/runs", {
        method: "POST",
        body: {
          table_name: tableName,
          ...(ruleIds !== undefined ? { rule_ids: ruleIds } : {}),
        },
      }),
    onSuccess: (data) => {
      // Seed detail cache with running summary so polling starts immediately
      queryClient.setQueryData<RunDetail>(["run", data.id], { ...data, results: [] });
      queryClient.invalidateQueries({ queryKey: ["runs", tableName] });
    },
  });
};

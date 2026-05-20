"use client";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "./api";
import type {
  CreateRuleRequest,
  NlRuleResponse,
  RuleRecord,
  RunDetail,
  SuggestResponse,
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
    mutationFn: (description: string) =>
      apiFetch<NlRuleResponse>("/rules/from-nl", {
        method: "POST",
        body: { table_name: tableName, description },
      }),
  });
};

export const useTriggerRun = (tableName: string) => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiFetch<RunDetail>("/runs", {
        method: "POST",
        body: { table_name: tableName },
      }),
    onSuccess: (data) => {
      // Pre-seed detail cache so useRunDetail returns without a second fetch
      queryClient.setQueryData(["run", data.id], data);
      // Invalidate summary list so it refetches and surfaces the new run ID
      queryClient.invalidateQueries({ queryKey: ["runs", tableName] });
    },
  });
};

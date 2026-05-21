import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "./api";
import type { TableInfo, TableDetail, SampleResponse, RuleRecord, RunSummary, RunDetail } from "../types/api";

export const useTables = () =>
  useQuery({
    queryKey: ["tables"],
    queryFn: () => apiFetch<TableInfo[]>("/tables"),
  });

export const useTableSchema = (name: string) =>
  useQuery({
    queryKey: ["tables", name],
    queryFn: () => apiFetch<TableDetail>(`/tables/${name}`),
    enabled: !!name,
  });

export const useTableSample = (name: string) =>
  useQuery({
    queryKey: ["tables", name, "sample"],
    queryFn: () => apiFetch<SampleResponse>(`/tables/${name}/sample`),
    enabled: !!name,
  });

export const useRules = (tableName: string) =>
  useQuery({
    queryKey: ["rules", tableName],
    queryFn: () => apiFetch<RuleRecord[]>(`/rules?table_name=${encodeURIComponent(tableName)}`),
    enabled: !!tableName,
  });

export const useRunSummaries = (tableName: string) =>
  useQuery({
    queryKey: ["runs", tableName],
    queryFn: () =>
      apiFetch<RunSummary[]>(
        `/runs?table_name=${encodeURIComponent(tableName)}&limit=1`
      ),
    enabled: !!tableName,
  });

export const useRunDetail = (runId: number | null) =>
  useQuery({
    queryKey: ["run", runId],
    queryFn: () => apiFetch<RunDetail>(`/runs/${runId}`),
    enabled: runId != null,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "running" ? 1000 : false;
    },
  });

import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "./api";
import type { TableInfo, TableDetail, SampleResponse, RuleRecord } from "../types/api";

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

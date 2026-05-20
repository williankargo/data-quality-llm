export interface ColumnInfo {
  name: string;
  data_type: string;
  is_nullable: boolean;
  column_default: string | null;
}

export interface TableInfo {
  name: string;
  row_count: number;
  column_count: number;
}

export interface TableDetail {
  name: string;
  row_count: number;
  columns: ColumnInfo[];
}

export interface SampleResponse {
  rows: Record<string, unknown>[];
  limit: number;
}

export interface ApiErrorData {
  code: string;
  user_message: string;
  technical_detail: string;
}

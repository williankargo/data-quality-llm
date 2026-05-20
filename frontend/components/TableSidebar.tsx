"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTables } from "@/lib/queries";
import { LoadingSkeleton } from "./LoadingSkeleton";
import { ApiError } from "@/lib/api";

export function TableSidebar() {
  const { data: tables, isLoading, error } = useTables();
  const pathname = usePathname();

  return (
    <div className="p-4">
      <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">
        Tables
      </h2>
      {isLoading && <LoadingSkeleton lines={4} />}
      {error && (
        <p className="text-sm text-red-500">
          {error instanceof ApiError ? error.user_message : "Failed to load tables"}
        </p>
      )}
      {tables && (
        <ul className="space-y-1">
          {tables.map((table) => {
            const href = `/tables/${table.name}?tab=schema`;
            const isActive = pathname === `/tables/${table.name}`;
            return (
              <li key={table.name}>
                <Link
                  href={href}
                  className={`block px-3 py-2 rounded-md text-sm transition-colors ${
                    isActive
                      ? "bg-blue-50 text-blue-700 font-medium"
                      : "text-gray-700 hover:bg-gray-100"
                  }`}
                >
                  <span className="font-medium">{table.name}</span>
                  <span className="ml-2 text-xs text-gray-400">
                    {table.row_count.toLocaleString()} rows
                  </span>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

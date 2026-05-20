"use client";
import { Suspense } from "react";
import { useParams } from "next/navigation";
import { useSearchParams } from "next/navigation";
import { TableTabs } from "@/components/TableTabs";
import { LoadingSkeleton } from "@/components/LoadingSkeleton";

function TablePageInner() {
  const params = useParams<{ name: string }>();
  const searchParams = useSearchParams();
  const name = params.name;
  const tab = searchParams.get("tab") ?? "schema";
  return <TableTabs name={name} activeTab={tab} />;
}

export default function TablePage() {
  return (
    <Suspense fallback={<div className="p-6"><LoadingSkeleton lines={6} /></div>}>
      <TablePageInner />
    </Suspense>
  );
}

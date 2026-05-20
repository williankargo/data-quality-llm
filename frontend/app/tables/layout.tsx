import { TableSidebar } from "@/components/TableSidebar";

export default function TablesLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-screen bg-gray-50">
      <aside className="w-72 border-r bg-white overflow-y-auto shrink-0">
        <TableSidebar />
      </aside>
      <main className="flex-1 overflow-auto">{children}</main>
    </div>
  );
}

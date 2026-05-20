"use client";
import { useRouter } from "next/navigation";
import { SchemaView } from "./SchemaView";

const TABS = ["schema", "rules", "results"] as const;
type Tab = (typeof TABS)[number];

interface TableTabsProps {
  name: string;
  activeTab: string;
}

export function TableTabs({ name, activeTab }: TableTabsProps) {
  const router = useRouter();
  const tab = (TABS.includes(activeTab as Tab) ? activeTab : "schema") as Tab;

  const handleTabChange = (newTab: Tab) => {
    router.replace(`/tables/${name}?tab=${newTab}`);
  };

  return (
    <div className="flex flex-col h-full">
      {/* Tab bar */}
      <div className="border-b bg-white px-6 pt-4">
        <h1 className="text-lg font-semibold text-gray-900 mb-3">{name}</h1>
        <div className="flex gap-1">
          {TABS.map((t) => (
            <button
              key={t}
              onClick={() => handleTabChange(t)}
              className={`px-4 py-2 text-sm font-medium rounded-t-md border-b-2 transition-colors capitalize ${
                tab === t
                  ? "border-blue-600 text-blue-600"
                  : "border-transparent text-gray-500 hover:text-gray-700"
              }`}
            >
              {t}
            </button>
          ))}
        </div>
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-auto p-6">
        {tab === "schema" && <SchemaView name={name} />}
        {tab === "rules" && (
          <div className="text-gray-400 text-sm">Rule management coming in Day 2.</div>
        )}
        {tab === "results" && (
          <div className="text-gray-400 text-sm">Results dashboard coming in Day 2.</div>
        )}
      </div>
    </div>
  );
}

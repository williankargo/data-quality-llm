import type { ExplainResponse } from "@/types/api";

interface Props {
  data: ExplainResponse;
}

export function ResultExplainPanel({ data }: Props) {
  return (
    <div className="mt-3 p-3 bg-yellow-50 border border-yellow-200 rounded-md">
      <p className="text-xs font-semibold text-yellow-800 mb-1">AI Analysis</p>
      <p className="text-sm text-yellow-900">{data.explanation}</p>
      <ul className="mt-2 space-y-1">
        {data.possible_causes.map((cause, i) => (
          <li key={i} className="text-xs text-yellow-800 flex gap-1.5">
            <span aria-hidden>•</span>
            <span>{cause}</span>
          </li>
        ))}
      </ul>
      <p className="mt-2 text-xs font-medium text-yellow-900">
        Suggested action: {data.suggested_action}
      </p>
    </div>
  );
}

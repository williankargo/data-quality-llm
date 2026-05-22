import type { GeRule } from "@/types/api";

interface DiffLinesProps {
  original: GeRule;
  edited: GeRule;
}

interface FieldDiff {
  field: string;
  before: string;
  after: string;
}

function computeDiffs(original: GeRule, edited: GeRule): FieldDiff[] {
  const diffs: FieldDiff[] = [];

  if (original.expectation_type !== edited.expectation_type) {
    diffs.push({
      field: "expectation_type",
      before: original.expectation_type,
      after: edited.expectation_type,
    });
  }

  const origKwargs = JSON.stringify(original.kwargs, null, 2);
  const editedKwargs = JSON.stringify(edited.kwargs, null, 2);
  if (origKwargs !== editedKwargs) {
    diffs.push({ field: "kwargs", before: origKwargs, after: editedKwargs });
  }

  if (original.description !== edited.description) {
    diffs.push({
      field: "description",
      before: original.description,
      after: edited.description,
    });
  }

  return diffs;
}

export function DiffLines({ original, edited }: DiffLinesProps) {
  const diffs = computeDiffs(original, edited);

  if (diffs.length === 0) {
    return (
      <p className="text-xs text-gray-400 italic">No changes yet.</p>
    );
  }

  return (
    <div className="space-y-2">
      {diffs.map(({ field, before, after }) => (
        <div key={field} className="text-xs font-mono">
          <span className="text-gray-500 font-sans font-medium">{field}</span>
          <div className="mt-1 bg-red-50 border border-red-200 rounded px-2 py-1 line-through text-red-700 whitespace-pre-wrap break-all">
            {before}
          </div>
          <div className="mt-0.5 bg-green-50 border border-green-200 rounded px-2 py-1 text-green-800 whitespace-pre-wrap break-all">
            {after}
          </div>
        </div>
      ))}
    </div>
  );
}

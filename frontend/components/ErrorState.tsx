import { ApiError } from "@/lib/api";

const ERROR_CONFIG: Record<string, { title: string; causes: string[] }> = {
  TABLE_NOT_FOUND: {
    title: "Table Not Found",
    causes: [
      "The table name in the URL may be incorrect.",
      "The table may have been deleted from the database.",
    ],
  },
  DATABASE_UNAVAILABLE: {
    title: "Database Unavailable",
    causes: [
      "The database server may be temporarily unavailable.",
      "Your network connection may be unstable.",
      "The backend service may not be running.",
    ],
  },
  INTERNAL_ERROR: {
    title: "Unexpected Error",
    causes: [
      "The backend service encountered an unexpected error.",
      "Try refreshing the page or restarting the backend.",
    ],
  },
};

const DEFAULT_CONFIG = {
  title: "Something Went Wrong",
  causes: ["An unexpected error occurred. Please try again."],
};

interface ErrorStateProps {
  error: ApiError;
  onRetry?: () => void;
}

export function ErrorState({ error, onRetry }: ErrorStateProps) {
  const config = ERROR_CONFIG[error.code] ?? DEFAULT_CONFIG;

  return (
    <div className="rounded-lg border border-red-200 bg-red-50 p-6 max-w-lg">
      <div className="flex items-start gap-3">
        <span className="text-red-500 text-xl">&#9888;</span>
        <div className="flex-1">
          <h3 className="font-semibold text-red-800">{config.title}</h3>
          <p className="text-sm text-red-700 mt-1">{error.user_message}</p>
          <ul className="mt-3 space-y-1">
            {config.causes.map((cause, i) => (
              <li key={i} className="text-sm text-red-600 flex items-start gap-2">
                <span>•</span>
                <span>{cause}</span>
              </li>
            ))}
          </ul>
          {onRetry && (
            <button
              onClick={onRetry}
              className="mt-4 px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-md hover:bg-red-700 transition-colors"
            >
              Retry
            </button>
          )}
          {error.technical_detail && (
            <details className="mt-3">
              <summary className="text-xs text-red-500 cursor-pointer hover:text-red-700">
                Technical detail
              </summary>
              <pre className="mt-2 text-xs text-red-600 bg-red-100 p-2 rounded overflow-x-auto whitespace-pre-wrap">
                {error.technical_detail}
              </pre>
            </details>
          )}
        </div>
      </div>
    </div>
  );
}

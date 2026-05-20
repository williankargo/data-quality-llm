interface RunButtonProps {
  onClick: () => void;
  isLoading: boolean;
}

export function RunButton({ onClick, isLoading }: RunButtonProps) {
  return (
    <button
      onClick={onClick}
      disabled={isLoading}
      className="px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-md hover:bg-indigo-700 disabled:opacity-50 transition-colors flex items-center gap-2"
    >
      {isLoading ? (
        <>
          <span className="inline-block w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
          Running...
        </>
      ) : (
        <>&#9654; Run checks</>
      )}
    </button>
  );
}

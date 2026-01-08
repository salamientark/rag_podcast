'use client';

export const ListEpisodesToolResult = ({
  args,
}: {
  args: { beginning: string; podcast: string };
}) => {
  const beginningDate = args?.beginning ?? '...';
  const podcast = args?.podcast ?? '...';

  return (
    <div className="border rounded-xl p-3 text-sm flex flex-col gap-2">
      <div className="flex justify-between items-center">
        <div className="flex items-center gap-2">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="lucide lucide-search text-muted-foreground"
          >
            <circle cx="11" cy="11" r="8" />
            <path d="m21 21-4.3-4.3" />
          </svg>
          <span className="text-muted-foreground">
            Listed episodes from{' '}
            <strong className="text-foreground">{beginningDate}</strong>
            <span className="text-muted-foreground"> (podcast: {podcast})</span>
          </span>
        </div>
      </div>
    </div>
  );
};

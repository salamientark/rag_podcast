'use client';

import { useState } from 'react';
import { Button } from './ui/button';

export const PodcastQueryToolResult = ({
  args,
  result,
}: {
  args: { question: string };
  result: any;
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const query = args?.question ?? '...';
  const results = Array.isArray(result) ? result : [];
  const numResults = results.length;

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
            Searched podcast episodes for{' '}
            <strong className="text-foreground">&quot;{query}&quot;</strong>
          </span>
        </div>
        {numResults > 0 && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setIsOpen(!isOpen)}
            className="text-xs"
          >
            {isOpen ? 'Hide' : 'Show'} {numResults} result
            {numResults > 1 ? 's' : ''}
          </Button>
        )}
      </div>
      {isOpen && (
        <pre className="mt-2 p-2 bg-muted rounded-md overflow-x-auto text-xs">
          {JSON.stringify(result, null, 2)}
        </pre>
      )}
    </div>
  );
};

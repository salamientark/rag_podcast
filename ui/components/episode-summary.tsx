'use client';

import { useState } from 'react';
import { Button } from './ui/button';
import { ChevronDownIcon } from './icons';

/**
 * MCP tool response for get_episode_summary.
 * - `structuredContent.result`: Primary response format with the summary as a string.
 * - `content`: Fallback MCP format as an array of content blocks (e.g., [{type: 'text', text: '...'}]).
 * - `isError`: Set to true when summary retrieval failed.
 */
interface EpisodeSummaryResult {
  content?: Array<{ type: string; text: string }>;
  isError?: boolean;
  structuredContent?: { result: string };
}

export const EpisodeSummaryToolCall = ({
  args,
}: {
  args: { date: string; podcast: string; language?: string };
}) => {
  const date = args?.date ?? '...';
  const podcast = args?.podcast ?? '...';

  return (
    <div className="border rounded-xl p-3 text-sm flex flex-col gap-2 animate-pulse">
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
          className="text-muted-foreground"
        >
          <path d="M8 2h8" />
          <path d="M9 2v4" />
          <path d="M15 2v4" />
          <rect width="18" height="18" x="3" y="4" rx="2" />
          <path d="M3 10h18" />
        </svg>
        <span className="text-muted-foreground">
          Generating summary for{' '}
          <strong className="text-foreground">{date}</strong>
          <span className="text-muted-foreground"> (podcast: {podcast})</span>
        </span>
      </div>
    </div>
  );
};

export const EpisodeSummaryToolResult = ({
  args,
  result,
}: {
  args: { date: string; podcast: string; language?: string };
  result: EpisodeSummaryResult;
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const date = args?.date ?? '...';
  const podcast = args?.podcast ?? '...';

  const summaryText =
    result?.structuredContent?.result ??
	result?.content?.map((b) => b.text).join('') ?? '';

  // Detect errors from explicit flag or error-prefixed content
  const isError =
    result?.isError ??
    (typeof summaryText === 'string' && summaryText.startsWith('error:'));
  const hasContent = summaryText.length > 0;

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
            className={isError ? 'text-destructive' : 'text-muted-foreground'}
          >
            <path d="M8 2h8" />
            <path d="M9 2v4" />
            <path d="M15 2v4" />
            <rect width="18" height="18" x="3" y="4" rx="2" />
            <path d="M3 10h18" />
          </svg>
          <span className="text-muted-foreground">
            {isError
               ? 'Summary generation failed: '
               : 'Generated summary for: '}
            <strong className="text-foreground">{date}</strong>
            <span className="text-muted-foreground"> (podcast: {podcast})</span>
          </span>
        </div>
        {hasContent && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setIsOpen(!isOpen)}
            className="text-xs gap-1"
          >
             {isOpen ? 'Hide' : 'Show summary'}
            <span
              className={`transition-transform ${isOpen ? 'rotate-180' : ''}`}
            >
              <ChevronDownIcon size={14} />
            </span>
          </Button>
        )}
      </div>
      {isOpen && hasContent && (
        <pre className="mt-2 p-3 bg-muted/50 rounded-lg border whitespace-pre-wrap text-xs max-h-[50vh] overflow-auto">
        {summaryText}
        </pre>
      )}
    </div>
  );
};

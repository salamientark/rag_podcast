'use client';

import { useState } from 'react';
import { Button } from './ui/button';
import { Markdown } from './markdown';
import { ChevronDownIcon } from './icons';

/**
 * MCP tool response for ask_podcast.
 * - `structuredContent.result`: Primary response format with the query result as a string.
 * - `content`: Fallback MCP format as an array of content blocks (e.g., [{type: 'text', text: '...'}]).
 * - `isError`: Set to true when the query failed; in that case, content may contain error details.
 */
interface AskPodcastResult {
  content?: Array<{ type: string; text: string }>;
  isError?: boolean;
  structuredContent?: { result: string };
}

export const AskPodcastToolCall = ({ args }: { args: { question: string } }) => {
  const question = args?.question ?? '...';

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
          <ellipse cx="12" cy="5" rx="9" ry="3" />
          <path d="M3 5V19A9 3 0 0 0 21 19V5" />
          <path d="M3 12A9 3 0 0 0 21 12" />
        </svg>
        <span className="text-muted-foreground">
          Searching:{' '}
          <strong className="text-foreground">&quot;{question}&quot;</strong>
        </span>
      </div>
    </div>
  );
};

export const AskPodcastToolResult = ({
  args,
  result,
}: {
  args: { question: string };
  result: AskPodcastResult;
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const question = args?.question ?? '...';

  // Extract the text content from the result
  const textContent =
    result?.structuredContent?.result ?? result?.content?.[0]?.text ?? '';

  // Detect errors from explicit flag or error-prefixed content
  const isError = result?.isError ?? (typeof textContent === 'string' && textContent.startsWith('error:'));
  const hasContent = textContent.length > 0;

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
            <ellipse cx="12" cy="5" rx="9" ry="3" />
            <path d="M3 5V19A9 3 0 0 0 21 19V5" />
            <path d="M3 12A9 3 0 0 0 21 12" />
          </svg>
          <span className="text-muted-foreground">
            {isError ? 'Query failed: ' : 'Queried: '}
            <strong className="text-foreground">&quot;{question}&quot;</strong>
          </span>
        </div>
        {hasContent && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setIsOpen(!isOpen)}
            className="text-xs gap-1"
          >
            {isOpen ? 'Hide' : 'Show result'}
            <span
              className={`transition-transform ${isOpen ? 'rotate-180' : ''}`}
            >
              <ChevronDownIcon size={14} />
            </span>
          </Button>
        )}
      </div>
      {isOpen && hasContent && (
        <div className="mt-2 p-3 bg-muted/50 rounded-lg border">
          <Markdown>{textContent}</Markdown>
        </div>
      )}
    </div>
  );
};

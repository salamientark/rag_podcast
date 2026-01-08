'use client';

import { Button } from './ui/button';
import { useState } from 'react';

export const EpisodeInfoToolResult = ({
  args,
  result,
}: {
  args: { [key: string]: any };
  result: any;
}) => {
  const [isOpen, setIsOpen] = useState(false);
  let episodeTitle = '...';
  let episodeInfo: any = null;
  let errorMessage: string | null = null;

  const rawResult = result?.structuredContent?.result;
  if (rawResult) {
    // Check if result is an error string
    if (typeof rawResult === 'string' && rawResult.startsWith('error:')) {
      errorMessage = rawResult;
    } else {
      try {
        episodeInfo = JSON.parse(rawResult);
        episodeTitle = episodeInfo.title;
      } catch (e) {
        // If JSON parsing fails, treat the raw result as an error message
        errorMessage = typeof rawResult === 'string' ? rawResult : 'Failed to parse result';
      }
    }
  }

  const renderDetails = () => {
    if (errorMessage) {
      return (
        <div className="mt-2 p-3 bg-destructive/10 border border-destructive/20 rounded-md text-xs text-destructive">
          {errorMessage}
        </div>
      );
    }
    if (!episodeInfo) {
      return (
        <pre className="mt-2 p-2 bg-muted rounded-md overflow-x-auto text-xs">
          {JSON.stringify(result, null, 2)}
        </pre>
      );
    }
    const { title, date, duration, description, link } = episodeInfo;
    const cleanDescription =
      description
        ?.replace(/<[^>]+>/g, ' ')
        .replace(/&nbsp;/g, ' ')
        .replace(/\s\s+/g, ' ')
        .trim() || '';
    const descriptionSnippet =
      cleanDescription.substring(0, 250) +
      (cleanDescription.length > 250 ? '...' : '');

    return (
      <div className="mt-2 p-3 bg-muted rounded-md text-xs flex flex-col gap-3">
        <div>
          <p className="font-semibold text-foreground">Title</p>
          <p>{title}</p>
        </div>
        <div>
          <p className="font-semibold text-foreground">Date</p>
          <p>{new Date(date).toLocaleDateString()}</p>
        </div>
        <div>
          <p className="font-semibold text-foreground">Duration</p>
          <p>{duration}</p>
        </div>
        <div>
          <p className="font-semibold text-foreground">Description</p>
          <p className="whitespace-pre-wrap">{descriptionSnippet}</p>
        </div>
        <div>
          <p className="font-semibold text-foreground">Link</p>
          <a
            href={link}
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-500 underline hover:text-blue-600"
          >
            {link}
          </a>
        </div>
      </div>
    );
  };

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
            className={errorMessage ? "lucide lucide-alert-circle text-destructive" : "lucide lucide-search text-muted-foreground"}
          >
            {errorMessage ? (
              <>
                <circle cx="12" cy="12" r="10" />
                <line x1="12" x2="12" y1="8" y2="12" />
                <line x1="12" x2="12.01" y1="16" y2="16" />
              </>
            ) : (
              <>
                <circle cx="11" cy="11" r="8" />
                <path d="m21 21-4.3-4.3" />
              </>
            )}
          </svg>
          <span className={errorMessage ? "text-destructive" : "text-muted-foreground"}>
            {errorMessage ? (
              'Failed to retrieve episode info'
            ) : (
              <>
                Retrieved info for episode:{' '}
                <strong className="text-foreground">
                  &quot;{episodeTitle}&quot;
                </strong>
              </>
            )}
          </span>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setIsOpen(!isOpen)}
          className="text-xs"
        >
          {isOpen ? 'Hide' : 'Show'} details
        </Button>
      </div>
      {isOpen && renderDetails()}
    </div>
  );
};

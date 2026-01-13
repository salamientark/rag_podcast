import { LangfuseSpanProcessor, type ShouldExportSpan } from '@langfuse/otel';
import { NodeTracerProvider } from '@opentelemetry/sdk-trace-node';

// Filter out noisy Next.js infrastructure spans.
const shouldExportSpan: ShouldExportSpan = (span) => {
  return span.otelSpan.instrumentationScope.name !== 'next.js';
};

export const langfuseSpanProcessor = new LangfuseSpanProcessor({
  shouldExportSpan,
});

const tracerProvider = new NodeTracerProvider({
  spanProcessors: [langfuseSpanProcessor],
});

// Next.js instrumentation entrypoint.
export function register() {
  tracerProvider.register();
}

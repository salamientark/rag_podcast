import { NodeSDK } from '@opentelemetry/sdk-node';
import { LangfuseSpanProcessor } from '@langfuse/otel';

export function register() {
  if (process.env.NEXT_RUNTIME === 'nodejs') {
	// Register OpenTelemetry for Langfuse tracing
    const sdk = new NodeSDK({
      spanProcessors: [new LangfuseSpanProcessor()],
    });

    sdk.start();

	const gracefulShutdown = () => {
	      sdk.shutdown()
	        .then(() => console.log('Tracing terminated'))
	        .catch((error) => console.error('Error terminating tracing', error))
	        .finally(() => process.exit(0));
	    };

    process.on('SIGTERM', gracefulShutdown);

    process.on('SIGINT', gracefulShutdown);
  }
}

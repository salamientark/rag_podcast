import { NodeTracerProvider } from '@opentelemetry/sdk-trace-node';

const tracerProvider = new NodeTracerProvider();

export function register() {
  tracerProvider.register();
}

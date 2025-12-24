# Logger Module

## Purpose

Centralized logging utilities providing consistent, configurable logging across the rag_podcast project. Offers both programmatic logger setup and decorators for automatic function instrumentation.

## Key Components

### `setup_logging(logger_name, log_file, verbose, level)`

Core function that creates and configures loggers.

- Creates log directories automatically
- Adds file handler for persistent logging
- Optionally adds console handler for verbose mode
- Returns existing logger if already configured (prevents duplicate handlers)

### `log_function(logger_name, log_file, level, log_args, log_result, log_execution_time)`

Primary decorator for instrumenting functions with logging.

- Logs entry, exit, execution time, and exceptions
- Configurable: can log arguments, results, both, or neither
- Default behavior: Logs execution time only

### Convenience Decorators

- `log_with_timer(logger_name)`: Simple entry/exit with timing
- `log_detailed(logger_name, log_file)`: Logs everything (args + result + time)

## Important Patterns

### Logger Name Resolution

If `logger_name=None` in decorator, uses `func.__module__` as the logger name.

### Handler Deduplication

`setup_logging` checks `logger.handlers` before adding new ones. Prevents duplicate log entries.

### Exception Handling

Decorated functions automatically log exceptions with full stack traces (`exc_info=True`) before re-raising.

## Gotchas

1. **Mutable Default for logger_name**: Decorator uses `nonlocal logger_name`. If `None`, gets set to `func.__module__` on first call.

2. **Handler Accumulation**: Python's logging has global state. Loggers persist across module reloads.

3. **Verbose Mode**: When `verbose=True`, logger level is set to DEBUG regardless of `level` parameter.

4. **Log File Creation**: Files created eagerly when logger set up, not lazily on first log.

5. **Argument Repr**: When `log_args=True`, uses `repr()`. Be cautious with large objects.

6. **Time Precision**: Uses `time.time()` with 2 decimal places. Use `time.perf_counter()` for microsecond precision.

## Usage Example

```python
from src.logger import setup_logging, log_function

logger = setup_logging("my_module", "logs/my_module.log", verbose=True)
logger.info("Starting process")

@log_function(logger_name="my_module", log_args=True, log_execution_time=True)
def process_data(data):
    logger.debug("Processing item")
    return result
```

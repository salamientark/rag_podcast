# Logging System

Centralized logging with flexible decorators for the rag_podcast project.

## Quick Start

```python
from src.logger import setup_logging, log_function

# Setup logger
logger = setup_logging("my_module", "logs/my_module.log")

# Decorate functions for automatic logging
@log_function(logger_name="my_module", log_execution_time=True)
def my_function(arg1, arg2):
    logger.info("Processing...")
    return result
```

## Setup Logging

```python
setup_logging(
    logger_name="my_module",      # Logger name
    log_file="logs/my_module.log", # Log file path
    verbose=True                   # Enable console output (optional)
)
```

## Decorator Options

### Basic Usage

```python
# Just timing
@log_function(logger_name="my_module", log_execution_time=True)
def process_data(data):
    pass
```

### Log Arguments

```python
@log_function(logger_name="my_module", log_args=True)
def calculate(x, y):
    return x + y
```

### Log Arguments and Results

```python
@log_function(
    logger_name="my_module",
    log_args=True,
    log_result=True,
    log_execution_time=True
)
def transform(data):
    return processed_data
```

### Custom Log File

```python
@log_function(
    logger_name="custom_task",
    log_file="logs/custom.log",
    log_args=True
)
def special_task(task_id):
    return {"status": "done"}
```

## Convenience Decorators

```python
from src.logger import log_with_timer, log_detailed

# Simple timer
@log_with_timer("my_module")
def quick_task():
    pass

# Everything: args, result, timing
@log_detailed("my_module", log_file="logs/detailed.log")
def complex_task(data):
    return result
```

## Decorator Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `logger_name` | str | module name | Logger name |
| `log_file` | str | None | Custom log file |
| `level` | int | INFO | Log level |
| `log_args` | bool | False | Log arguments |
| `log_result` | bool | False | Log return value |
| `log_execution_time` | bool | True | Log duration |

## Features

- **Automatic timing** - Execution time logged by default
- **Exception logging** - Exceptions logged with full stack traces
- **Flexible configuration** - Customize per function
- **Custom log files** - Different functions can use different files
- **Hybrid approach** - Mix decorators with manual logging

## Examples

See real usage throughout the codebase:
- `src/ingestion/audio_scrap.py` - Download operations logging
- `src/ingestion/sync_episodes.py` - RSS sync logging  
- `src/transcription/transcript.py` - Transcription process logging
- `src/pipeline/orchestrator.py` - Pipeline orchestration logging

## Best Practices

1. **Use descriptive logger names**: `"audio_scraper"` not `"logger1"`
2. **Be selective with arg/result logging**: Only when debugging
3. **Use custom log files for subsystems**: Separate concerns
4. **Combine with manual logging**: Decorators for entry/exit, manual for progress
5. **Don't over-decorate**: Only important entry points need decorators

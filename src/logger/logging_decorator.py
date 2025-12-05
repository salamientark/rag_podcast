"""
Centralized Logging Utilities and Decorators

Provides reusable logging setup and function decorators for consistent logging
across the rag_podcast project.

Usage:
    from src.utils import setup_logging, log_function

    # Setup logging for a module
    logger = setup_logging(
        logger_name="my_module",
        log_file="logs/my_module.log",
        verbose=True
    )

    # Decorate functions for automatic logging
    @log_function(
        logger_name="my_module",
        log_file="logs/custom.log",
        log_args=True,
        log_result=False
    )
    def my_function(arg1, arg2):
        # Your code here
        pass
"""

import functools
import logging
import time
from pathlib import Path
from typing import Optional, Callable, Any


def setup_logging(
    logger_name: str,
    log_file: str = "logs/app.log",
    verbose: bool = False,
    level: int = logging.INFO,
) -> logging.Logger:
    """
    Set up logging with file and optional console handlers.

    Args:
        logger_name: Name for the logger (e.g., "audio_scraper")
        log_file: Path to log file (default: "logs/app.log")
        verbose: If True, add console handler with DEBUG level (default: False)
        level: Base logging level (default: logging.INFO)

    Returns:
        Configured logger instance

    Example:
        logger = setup_logging("my_module", "logs/my_module.log", verbose=True)
        logger.info("Module started")
    """
    logger = logging.getLogger(logger_name)

    # Avoid adding multiple handlers if already configured
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG if verbose else level)

    # Create logs directory if needed
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # File handler for detailed logging
    file_handler = logging.FileHandler(log_path)
    file_handler.setLevel(level)
    file_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    # Console handler for verbose mode
    if verbose:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)
        console_formatter = logging.Formatter("DEBUG: %(message)s")
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

    return logger


def log_function(
    logger_name: Optional[str] = None,
    log_file: Optional[str] = None,
    level: int = logging.INFO,
    log_args: bool = False,
    log_result: bool = False,
    log_execution_time: bool = True,
) -> Callable:
    """
    Decorator to automatically log function entry, exit, execution time, and exceptions.

    Args:
        logger_name: Custom logger name (if None, uses the decorated function's module name)
        log_file: Optional custom log file path (if None, uses existing logger config)
        level: Log level for entry/exit messages (default: logging.INFO)
        log_args: If True, log function arguments (default: False)
        log_result: If True, log return value (default: False)
        log_execution_time: If True, log execution duration (default: True)

    Returns:
        Decorated function with logging

    Example:
        @log_function(logger_name="audio_scraper", log_args=True, log_execution_time=True)
        def download_episode(episode_number, title, url):
            # Your code here
            pass

    Example with custom log file:
        @log_function(
            logger_name="custom_task",
            log_file="logs/custom_task.log",
            log_args=True,
            log_result=True
        )
        def process_data(data):
            return processed_data
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            # Determine logger to use
            nonlocal logger_name
            if logger_name is None:
                logger_name = func.__module__

            # Get or create logger
            if log_file:
                # Setup new logger with custom log file
                logger = setup_logging(
                    logger_name=f"{logger_name}.{func.__name__}",
                    log_file=log_file,
                    level=level,
                )
            else:
                # Use existing logger or create default
                logger = logging.getLogger(logger_name)
                if not logger.handlers:
                    logger = setup_logging(logger_name, level=level)

            # Build log message
            func_name = func.__name__
            log_msg = f"Calling {func_name}"

            # Optionally log arguments
            if log_args and (args or kwargs):
                args_repr = [repr(a) for a in args]
                kwargs_repr = [f"{k}={v!r}" for k, v in kwargs.items()]
                all_args = ", ".join(args_repr + kwargs_repr)
                log_msg += f" with args: {all_args}"

            logger.log(level, log_msg)

            # Track execution time
            start_time = time.time()

            try:
                # Execute function
                result = func(*args, **kwargs)

                # Calculate execution time
                execution_time = time.time() - start_time

                # Build completion message
                completion_msg = f"Completed {func_name}"

                if log_execution_time:
                    completion_msg += f" in {execution_time:.2f}s"

                if log_result:
                    completion_msg += f" with result: {result!r}"

                logger.log(level, completion_msg)

                return result

            except Exception as e:
                # Log exception with execution time
                execution_time = time.time() - start_time
                logger.error(
                    f"Exception in {func_name} after {execution_time:.2f}s: {type(e).__name__}: {e}",
                    exc_info=True,
                )
                raise

        return wrapper

    return decorator


# Convenience decorators for common use cases


def log_with_timer(logger_name: Optional[str] = None) -> Callable:
    """
    Simple decorator that logs function entry/exit with execution time.

    Example:
        @log_with_timer("audio_scraper")
        def download_episode(episode_number, title, url):
            # Your code here
            pass
    """
    return log_function(
        logger_name=logger_name,
        log_args=False,
        log_result=False,
        log_execution_time=True,
    )


def log_detailed(
    logger_name: Optional[str] = None, log_file: Optional[str] = None
) -> Callable:
    """
    Decorator that logs everything: args, result, and execution time.

    Example:
        @log_detailed("data_processor", log_file="logs/detailed.log")
        def process_data(data):
            return processed_data
    """
    return log_function(
        logger_name=logger_name,
        log_file=log_file,
        log_args=True,
        log_result=True,
        log_execution_time=True,
    )

"""
Custom exceptions and error handling utilities for poor-cli
"""

import logging
from pathlib import Path
from typing import Optional


class PoorCLIError(Exception):
    """Base exception for all poor-cli errors"""
    def __init__(self, message: str, details: Optional[str] = None):
        self.message = message
        self.details = details
        super().__init__(self.message)

    def __str__(self):
        if self.details:
            return f"{self.message}\nDetails: {self.details}"
        return self.message


class APIError(PoorCLIError):
    """Raised when API calls fail"""
    pass


class APIConnectionError(APIError):
    """Raised when cannot connect to API"""
    pass


class APITimeoutError(APIError):
    """Raised when API call times out"""
    pass


class APIRateLimitError(APIError):
    """Raised when API rate limit is exceeded"""
    pass


class FileOperationError(PoorCLIError):
    """Base exception for file operation errors"""
    pass


class FileNotFoundError(FileOperationError):
    """Raised when file is not found"""
    pass


class FilePermissionError(FileOperationError):
    """Raised when lacking permissions for file operation"""
    pass


class InvalidPathError(FileOperationError):
    """Raised when path is invalid or unsafe"""
    pass


class PathTraversalError(InvalidPathError):
    """Raised when path traversal attempt is detected"""
    pass


class ToolExecutionError(PoorCLIError):
    """Raised when tool execution fails"""
    def __init__(self, tool_name: str, message: str, details: Optional[str] = None):
        self.tool_name = tool_name
        super().__init__(f"Tool '{tool_name}' failed: {message}", details)


class CommandExecutionError(PoorCLIError):
    """Raised when bash command execution fails"""
    def __init__(self, command: str, message: str, return_code: Optional[int] = None):
        self.command = command
        self.return_code = return_code
        details = f"Command: {command}"
        if return_code is not None:
            details += f"\nExit code: {return_code}"
        super().__init__(message, details)


class ValidationError(PoorCLIError):
    """Raised when input validation fails"""
    pass


class ConfigurationError(PoorCLIError):
    """Raised when configuration is invalid"""
    pass


def setup_logger(name: str = "poor_cli", log_file: Optional[str] = None,
                 level: int = logging.INFO) -> logging.Logger:
    """
    Setup a logger with consistent formatting

    Args:
        name: Logger name
        log_file: Optional file path for logging
        level: Logging level

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Clear existing handlers
    logger.handlers.clear()

    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler if specified
    if log_file:
        try:
            file_handler = logging.FileHandler(log_file)
            file_handler.setLevel(level)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except Exception as e:
            logger.warning(f"Could not create log file {log_file}: {e}")

    return logger


def validate_file_path(file_path: str, base_path: Optional[Path] = None,
                      must_exist: bool = False, must_be_file: bool = False,
                      must_be_dir: bool = False) -> Path:
    """
    Validate and sanitize file paths to prevent path traversal attacks

    Args:
        file_path: Path to validate
        base_path: Base directory to restrict access to (defaults to cwd)
        must_exist: If True, raise error if path doesn't exist
        must_be_file: If True, raise error if path is not a file
        must_be_dir: If True, raise error if path is not a directory

    Returns:
        Resolved and validated Path object

    Raises:
        InvalidPathError: If path is invalid
        PathTraversalError: If path attempts to traverse outside base_path
        FileNotFoundError: If must_exist=True and path doesn't exist
        ValidationError: If path doesn't meet requirements
    """
    if not file_path or not isinstance(file_path, str):
        raise InvalidPathError("File path must be a non-empty string")

    try:
        # Expand user directory and resolve to absolute path
        path = Path(file_path).expanduser().resolve()
    except (ValueError, RuntimeError) as e:
        raise InvalidPathError(f"Invalid path: {file_path}", str(e))

    # Check for path traversal if base_path is provided
    if base_path:
        try:
            base = base_path.resolve()
            # Check if path is within base_path
            path.relative_to(base)
        except ValueError:
            raise PathTraversalError(
                f"Path '{file_path}' attempts to access outside allowed directory",
                f"Base path: {base_path}\nResolved path: {path}"
            )

    # Check existence
    if must_exist and not path.exists():
        raise FileNotFoundError(f"Path does not exist: {file_path}")

    # Check if file
    if must_be_file and path.exists() and not path.is_file():
        raise ValidationError(f"Path is not a file: {file_path}")

    # Check if directory
    if must_be_dir and path.exists() and not path.is_dir():
        raise ValidationError(f"Path is not a directory: {file_path}")

    return path


def safe_read_file(file_path: Path, encoding: str = 'utf-8',
                   max_size_mb: int = 100) -> str:
    """
    Safely read file contents with size limits

    Args:
        file_path: Path to file
        encoding: File encoding
        max_size_mb: Maximum file size in MB

    Returns:
        File contents as string

    Raises:
        FilePermissionError: If lacking read permissions
        ValidationError: If file is too large
        FileOperationError: If read fails
    """
    try:
        # Check file size
        size_mb = file_path.stat().st_size / (1024 * 1024)
        if size_mb > max_size_mb:
            raise ValidationError(
                f"File too large: {size_mb:.2f}MB (max: {max_size_mb}MB)"
            )

        # Read file
        with open(file_path, 'r', encoding=encoding) as f:
            return f.read()

    except PermissionError as e:
        raise FilePermissionError(f"No read permission for: {file_path}", str(e))
    except UnicodeDecodeError as e:
        raise FileOperationError(
            f"Cannot decode file with {encoding} encoding: {file_path}",
            str(e)
        )
    except OSError as e:
        raise FileOperationError(f"Error reading file: {file_path}", str(e))


def safe_write_file(file_path: Path, content: str, encoding: str = 'utf-8',
                    create_dirs: bool = True) -> None:
    """
    Safely write content to file

    Args:
        file_path: Path to file
        content: Content to write
        encoding: File encoding
        create_dirs: Whether to create parent directories

    Raises:
        FilePermissionError: If lacking write permissions
        FileOperationError: If write fails
    """
    try:
        # Create parent directories if needed
        if create_dirs:
            file_path.parent.mkdir(parents=True, exist_ok=True)

        # Write file
        with open(file_path, 'w', encoding=encoding) as f:
            f.write(content)

    except PermissionError as e:
        raise FilePermissionError(f"No write permission for: {file_path}", str(e))
    except OSError as e:
        raise FileOperationError(f"Error writing file: {file_path}", str(e))

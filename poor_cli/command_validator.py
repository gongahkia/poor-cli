"""
Bash command validation and safety checking

AST-based validation to prevent dangerous command execution.
"""

import re
from typing import List, Dict, Any, Optional, Tuple
from enum import Enum
from dataclasses import dataclass

from poor_cli.exceptions import setup_logger

logger = setup_logger(__name__)


class CommandRisk(Enum):
    """Risk levels for bash commands"""
    SAFE = "safe"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ValidationResult:
    """Result of command validation"""
    is_safe: bool
    risk_level: CommandRisk
    warnings: List[str]
    blocked_patterns: List[str]
    suggested_alternative: Optional[str] = None


class CommandValidator:
    """Validates bash commands for safety"""

    # Dangerous patterns that should never be allowed
    CRITICAL_PATTERNS = [
        r'rm\s+-rf\s+/',  # Recursive delete from root
        r'mkfs',  # Format filesystem
        r'dd\s+if=/dev/zero',  # Disk wipe
        r'fork\s*bomb|:\(\)\{',  # Fork bomb
        r'>\s*/dev/sd[a-z]',  # Write directly to disk
        r'chmod\s+777\s+/',  # Chmod entire filesystem
        r'chown\s+.*\s+/',  # Chown entire filesystem
    ]

    # High risk patterns that require approval
    HIGH_RISK_PATTERNS = [
        r'rm\s+-rf',  # Recursive delete
        r'rm\s+-fr',  # Recursive delete (reversed flags)
        r'sudo\s+rm',  # Delete with elevated privileges
        r'curl.*\|\s*bash',  # Pipe to bash
        r'wget.*\|\s*sh',  # Pipe to shell
        r'eval\s+',  # Evaluate arbitrary code
        r'exec\s+',  # Execute replacing shell
        r'\${.*}',  # Variable expansion (potential injection)
        r'`.*`',  # Command substitution
        r'\$\(',  # Command substitution
    ]

    # Medium risk patterns
    MEDIUM_RISK_PATTERNS = [
        r'chmod\s+[0-7]{3,4}',  # Change permissions
        r'chown\s+',  # Change ownership
        r'kill\s+-9',  # Force kill
        r'pkill',  # Kill by name
        r'killall',  # Kill all processes
        r'systemctl\s+stop',  # Stop system service
        r'service\s+.*\s+stop',  # Stop service
        r'reboot',  # Reboot system
        r'shutdown',  # Shutdown system
        r'init\s+[06]',  # Reboot/shutdown via init
    ]

    # Commands that are generally safe
    SAFE_COMMANDS = {
        'ls', 'pwd', 'echo', 'cat', 'head', 'tail', 'grep', 'find',
        'which', 'whoami', 'date', 'cal', 'uptime', 'df', 'du',
        'wc', 'sort', 'uniq', 'cut', 'tr', 'sed', 'awk',
        'git status', 'git log', 'git diff', 'git show',
        'python --version', 'node --version', 'npm --version'
    }

    def __init__(self, enable_strict_mode: bool = False):
        """Initialize command validator

        Args:
            enable_strict_mode: If True, block all risky commands
        """
        self.enable_strict_mode = enable_strict_mode
        logger.info(f"Initialized command validator (strict_mode={enable_strict_mode})")

    def validate(self, command: str) -> ValidationResult:
        """Validate a bash command

        Args:
            command: Bash command to validate

        Returns:
            ValidationResult with safety assessment
        """
        command = command.strip()
        warnings = []
        blocked_patterns = []
        risk_level = CommandRisk.SAFE

        # Check for critical patterns first
        for pattern in self.CRITICAL_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                blocked_patterns.append(pattern)
                risk_level = CommandRisk.CRITICAL
                warnings.append(f"CRITICAL: Matched dangerous pattern: {pattern}")

        # If critical patterns found, immediately reject
        if risk_level == CommandRisk.CRITICAL:
            return ValidationResult(
                is_safe=False,
                risk_level=risk_level,
                warnings=warnings,
                blocked_patterns=blocked_patterns,
                suggested_alternative=self._suggest_safe_alternative(command)
            )

        # Check for high risk patterns
        for pattern in self.HIGH_RISK_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                blocked_patterns.append(pattern)
                risk_level = CommandRisk.HIGH
                warnings.append(f"HIGH RISK: Matched pattern: {pattern}")

        # Check for medium risk patterns
        if risk_level != CommandRisk.HIGH:
            for pattern in self.MEDIUM_RISK_PATTERNS:
                if re.search(pattern, command, re.IGNORECASE):
                    risk_level = CommandRisk.MEDIUM
                    warnings.append(f"MEDIUM RISK: Matched pattern: {pattern}")

        # Check if command starts with a safe command
        command_first_word = command.split()[0] if command else ""
        if command_first_word in self.SAFE_COMMANDS or command in self.SAFE_COMMANDS:
            if not warnings:  # Only if no risky patterns detected
                risk_level = CommandRisk.SAFE

        # Determine if safe based on risk level and strict mode
        is_safe = True
        if self.enable_strict_mode:
            is_safe = risk_level in [CommandRisk.SAFE, CommandRisk.LOW]
        else:
            is_safe = risk_level != CommandRisk.CRITICAL

        return ValidationResult(
            is_safe=is_safe,
            risk_level=risk_level,
            warnings=warnings,
            blocked_patterns=blocked_patterns,
            suggested_alternative=self._suggest_safe_alternative(command) if not is_safe else None
        )

    def _suggest_safe_alternative(self, command: str) -> Optional[str]:
        """Suggest a safer alternative for a dangerous command

        Args:
            command: Original dangerous command

        Returns:
            Suggested safe alternative or None
        """
        # rm -rf -> suggest specific file instead
        if re.search(r'rm\s+-rf\s+/', command):
            return "Specify exact directory/file instead of root '/'"

        if re.search(r'rm\s+-rf', command):
            return "Use 'rm -ri' for interactive deletion or specify exact paths"

        # curl | bash -> suggest download and inspect first
        if re.search(r'curl.*\|\s*bash', command) or re.search(r'wget.*\|\s*sh', command):
            return "Download the script first, inspect it, then execute manually"

        # chmod 777 -> suggest specific permissions
        if re.search(r'chmod\s+777', command):
            return "Use specific permissions (e.g., 644 for files, 755 for directories)"

        return None

    def simulate_command(self, command: str) -> Dict[str, Any]:
        """Simulate command execution without running it (dry-run)

        Args:
            command: Command to simulate

        Returns:
            Dictionary with simulation results
        """
        validation = self.validate(command)

        simulation = {
            "command": command,
            "would_execute": validation.is_safe,
            "risk_level": validation.risk_level.value,
            "warnings": validation.warnings,
            "estimated_effects": self._estimate_effects(command)
        }

        return simulation

    def _estimate_effects(self, command: str) -> List[str]:
        """Estimate the effects of a command

        Args:
            command: Command to analyze

        Returns:
            List of estimated effects
        """
        effects = []

        # File operations
        if re.search(r'\brm\b', command):
            effects.append("Will delete files/directories")

        if re.search(r'\bmv\b', command):
            effects.append("Will move/rename files")

        if re.search(r'\bcp\b', command):
            effects.append("Will copy files")

        if re.search(r'\btouch\b', command):
            effects.append("Will create/update file timestamps")

        if re.search(r'\bmkdir\b', command):
            effects.append("Will create directories")

        # Permission changes
        if re.search(r'\bchmod\b', command):
            effects.append("Will modify file permissions")

        if re.search(r'\bchown\b', command):
            effects.append("Will change file ownership")

        # Process operations
        if re.search(r'\bkill\b', command):
            effects.append("Will terminate processes")

        # Network operations
        if re.search(r'\bcurl\b|\bwget\b', command):
            effects.append("Will make network requests")

        # System operations
        if re.search(r'\breboot\b|\bshutdown\b', command):
            effects.append("Will affect system power state")

        return effects if effects else ["Read-only operation"]


# Global validator instance
_command_validator: Optional[CommandValidator] = None


def get_command_validator(strict_mode: bool = False) -> CommandValidator:
    """Get global command validator instance

    Args:
        strict_mode: Enable strict validation mode

    Returns:
        CommandValidator instance
    """
    global _command_validator
    if _command_validator is None:
        _command_validator = CommandValidator(enable_strict_mode=strict_mode)
    return _command_validator

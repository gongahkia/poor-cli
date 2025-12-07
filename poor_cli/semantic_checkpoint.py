"""
Semantic Checkpointing for poor-cli

Intelligent checkpoint creation based on code semantics:
- Auto-checkpoint after refactorings (function extractions, renames, moves)
- Semantic tagging based on operation type
- Checkpoint consolidation to reduce storage
"""

import ast
import re
import difflib
from pathlib import Path
from typing import List, Dict, Any, Optional, Set, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
from collections import defaultdict

from poor_cli.checkpoint import CheckpointManager, Checkpoint
from poor_cli.exceptions import setup_logger

logger = setup_logger(__name__)


@dataclass
class CodeChange:
    """Represents a semantic code change"""
    change_type: str  # 'rename', 'extract', 'move', 'refactor', 'add', 'delete'
    file_path: str
    old_name: Optional[str] = None
    new_name: Optional[str] = None
    lines_changed: int = 0
    complexity_delta: int = 0
    metadata: Dict[str, Any] = None


class SemanticAnalyzer:
    """Analyzes code changes for semantic meaning"""

    def __init__(self):
        self.refactor_patterns = {
            'extract_function': re.compile(r'def\s+(\w+)\s*\('),
            'extract_class': re.compile(r'class\s+(\w+)\s*[\(:]'),
            'rename_function': re.compile(r'def\s+(\w+)\s*\('),
            'rename_class': re.compile(r'class\s+(\w+)\s*[\(:]'),
            'rename_variable': re.compile(r'(\w+)\s*='),
        }

    def analyze_file_change(
        self,
        file_path: str,
        old_content: str,
        new_content: str
    ) -> List[CodeChange]:
        """Analyze changes between two versions of a file

        Args:
            file_path: Path to the file
            old_content: Original content
            new_content: New content

        Returns:
            List of detected code changes
        """
        changes = []

        # Calculate line changes
        old_lines = old_content.splitlines()
        new_lines = new_content.splitlines()
        diff = list(difflib.unified_diff(old_lines, new_lines, lineterm=''))

        lines_changed = sum(1 for line in diff if line.startswith('+') or line.startswith('-'))

        # Detect refactorings based on file extension
        ext = Path(file_path).suffix

        if ext == '.py':
            changes.extend(self._analyze_python_changes(file_path, old_content, new_content))
        elif ext in ['.js', '.ts', '.jsx', '.tsx']:
            changes.extend(self._analyze_javascript_changes(file_path, old_content, new_content))

        # If no specific refactorings detected, classify as general change
        if not changes:
            change_type = self._classify_general_change(old_lines, new_lines, lines_changed)
            changes.append(CodeChange(
                change_type=change_type,
                file_path=file_path,
                lines_changed=lines_changed
            ))

        return changes

    def _analyze_python_changes(
        self,
        file_path: str,
        old_content: str,
        new_content: str
    ) -> List[CodeChange]:
        """Analyze Python-specific code changes"""
        changes = []

        try:
            # Parse old and new AST
            old_tree = ast.parse(old_content)
            new_tree = ast.parse(new_content)

            # Extract function and class definitions
            old_functions = self._extract_functions(old_tree)
            new_functions = self._extract_functions(new_tree)

            old_classes = self._extract_classes(old_tree)
            new_classes = self._extract_classes(new_tree)

            # Detect function extractions (new functions)
            new_func_names = set(new_functions.keys()) - set(old_functions.keys())
            if new_func_names and len(old_functions) > 0:
                for name in new_func_names:
                    changes.append(CodeChange(
                        change_type='extract_function',
                        file_path=file_path,
                        new_name=name,
                        metadata={'function_name': name}
                    ))

            # Detect function renames (similar complexity, different names)
            if len(old_functions) == len(new_functions):
                renamed = self._detect_renames(old_functions, new_functions)
                for old_name, new_name in renamed:
                    changes.append(CodeChange(
                        change_type='rename_function',
                        file_path=file_path,
                        old_name=old_name,
                        new_name=new_name,
                        metadata={'old_name': old_name, 'new_name': new_name}
                    ))

            # Detect class extractions
            new_class_names = set(new_classes.keys()) - set(old_classes.keys())
            if new_class_names and len(old_classes) > 0:
                for name in new_class_names:
                    changes.append(CodeChange(
                        change_type='extract_class',
                        file_path=file_path,
                        new_name=name,
                        metadata={'class_name': name}
                    ))

        except SyntaxError as e:
            logger.debug(f"Syntax error parsing Python file {file_path}: {e}")
        except Exception as e:
            logger.debug(f"Error analyzing Python changes: {e}")

        return changes

    def _analyze_javascript_changes(
        self,
        file_path: str,
        old_content: str,
        new_content: str
    ) -> List[CodeChange]:
        """Analyze JavaScript/TypeScript-specific code changes"""
        changes = []

        # Simple pattern-based analysis for JS/TS
        old_functions = re.findall(r'function\s+(\w+)\s*\(', old_content)
        new_functions = re.findall(r'function\s+(\w+)\s*\(', new_content)

        old_arrow_funcs = re.findall(r'const\s+(\w+)\s*=\s*\([^)]*\)\s*=>', old_content)
        new_arrow_funcs = re.findall(r'const\s+(\w+)\s*=\s*\([^)]*\)\s*=>', new_content)

        old_all = set(old_functions + old_arrow_funcs)
        new_all = set(new_functions + new_arrow_funcs)

        # Detect new functions
        new_names = new_all - old_all
        if new_names and len(old_all) > 0:
            for name in new_names:
                changes.append(CodeChange(
                    change_type='extract_function',
                    file_path=file_path,
                    new_name=name,
                    metadata={'function_name': name}
                ))

        return changes

    def _extract_functions(self, tree: ast.AST) -> Dict[str, int]:
        """Extract function names and their complexity from AST"""
        functions = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                complexity = len(list(ast.walk(node)))
                functions[node.name] = complexity
        return functions

    def _extract_classes(self, tree: ast.AST) -> Dict[str, int]:
        """Extract class names and their complexity from AST"""
        classes = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                complexity = len(list(ast.walk(node)))
                classes[node.name] = complexity
        return classes

    def _detect_renames(
        self,
        old_items: Dict[str, int],
        new_items: Dict[str, int]
    ) -> List[Tuple[str, str]]:
        """Detect renamed items based on complexity similarity"""
        renames = []

        old_names = set(old_items.keys())
        new_names = set(new_items.keys())

        # Items that disappeared
        removed = old_names - new_names
        # Items that appeared
        added = new_names - old_names

        if not removed or not added:
            return renames

        # Match by complexity
        for old_name in removed:
            old_complexity = old_items[old_name]
            # Find new items with similar complexity (±20%)
            for new_name in added:
                new_complexity = new_items[new_name]
                if abs(new_complexity - old_complexity) / old_complexity < 0.2:
                    renames.append((old_name, new_name))
                    break

        return renames

    def _classify_general_change(
        self,
        old_lines: List[str],
        new_lines: List[str],
        lines_changed: int
    ) -> str:
        """Classify general changes when no specific refactoring detected"""
        if not old_lines:
            return 'add'
        if not new_lines:
            return 'delete'

        # Calculate change ratio
        change_ratio = lines_changed / max(len(old_lines), len(new_lines))

        if change_ratio > 0.5:
            return 'major_refactor'
        elif change_ratio > 0.2:
            return 'refactor'
        else:
            return 'modify'


class SemanticCheckpointManager:
    """Checkpoint manager with semantic awareness"""

    def __init__(self, checkpoint_manager: CheckpointManager):
        """Initialize semantic checkpoint manager

        Args:
            checkpoint_manager: Base checkpoint manager
        """
        self.checkpoint_manager = checkpoint_manager
        self.semantic_analyzer = SemanticAnalyzer()
        self.change_history: List[CodeChange] = []

    def create_semantic_checkpoint(
        self,
        file_paths: List[str],
        old_contents: Dict[str, str],
        new_contents: Dict[str, str],
        operation_description: str = "Semantic checkpoint"
    ) -> Checkpoint:
        """Create a checkpoint with semantic analysis

        Args:
            file_paths: List of files that changed
            old_contents: Dictionary mapping file paths to old content
            new_contents: Dictionary mapping file paths to new content
            operation_description: Human-readable description

        Returns:
            Created checkpoint
        """
        # Analyze changes
        all_changes = []
        for file_path in file_paths:
            old_content = old_contents.get(file_path, "")
            new_content = new_contents.get(file_path, "")

            if old_content or new_content:
                changes = self.semantic_analyzer.analyze_file_change(
                    file_path, old_content, new_content
                )
                all_changes.extend(changes)

        # Generate semantic tags
        tags = self._generate_tags(all_changes)

        # Determine operation type
        operation_type = self._determine_operation_type(all_changes)

        # Generate description
        if not operation_description or operation_description == "Semantic checkpoint":
            operation_description = self._generate_description(all_changes)

        # Record changes
        self.change_history.extend(all_changes)

        # Create checkpoint with semantic metadata
        checkpoint = self.checkpoint_manager.create_checkpoint(
            file_paths=file_paths,
            description=operation_description,
            operation_type=operation_type,
            tags=tags
        )

        # Add semantic metadata
        checkpoint.metadata['semantic_changes'] = [
            {
                'type': change.change_type,
                'file': change.file_path,
                'old_name': change.old_name,
                'new_name': change.new_name,
                'lines_changed': change.lines_changed
            }
            for change in all_changes
        ]

        logger.info(
            f"Created semantic checkpoint with {len(all_changes)} change(s): {operation_description}"
        )

        return checkpoint

    def _generate_tags(self, changes: List[CodeChange]) -> List[str]:
        """Generate semantic tags from code changes"""
        tags = set()

        for change in changes:
            tags.add(change.change_type)

            # Add specific tags
            if change.change_type in ['extract_function', 'extract_class']:
                tags.add('refactoring')
                tags.add('extraction')
            elif change.change_type in ['rename_function', 'rename_class', 'rename_variable']:
                tags.add('refactoring')
                tags.add('rename')
            elif change.change_type in ['major_refactor', 'refactor']:
                tags.add('refactoring')
            elif change.change_type == 'add':
                tags.add('new_code')
            elif change.change_type == 'delete':
                tags.add('removal')

        return sorted(list(tags))

    def _determine_operation_type(self, changes: List[CodeChange]) -> str:
        """Determine overall operation type from changes"""
        if not changes:
            return 'auto'

        change_types = [c.change_type for c in changes]

        # Priority: refactoring > add > modify > delete
        if any(t in ['extract_function', 'extract_class', 'rename_function', 'rename_class', 'major_refactor'] for t in change_types):
            return 'refactoring'
        elif all(t == 'add' for t in change_types):
            return 'addition'
        elif all(t == 'delete' for t in change_types):
            return 'deletion'
        else:
            return 'modification'

    def _generate_description(self, changes: List[CodeChange]) -> str:
        """Generate human-readable description from changes"""
        if not changes:
            return "No changes detected"

        # Group by change type
        by_type = defaultdict(list)
        for change in changes:
            by_type[change.change_type].append(change)

        descriptions = []

        # Function extractions
        if 'extract_function' in by_type:
            funcs = [c.new_name for c in by_type['extract_function'] if c.new_name]
            if funcs:
                descriptions.append(f"Extracted function(s): {', '.join(funcs[:3])}")

        # Function renames
        if 'rename_function' in by_type:
            renames = [(c.old_name, c.new_name) for c in by_type['rename_function'] if c.old_name and c.new_name]
            if renames:
                descriptions.append(f"Renamed: {renames[0][0]} → {renames[0][1]}")

        # Class extractions
        if 'extract_class' in by_type:
            classes = [c.new_name for c in by_type['extract_class'] if c.new_name]
            if classes:
                descriptions.append(f"Extracted class(es): {', '.join(classes[:3])}")

        # General refactoring
        if 'refactor' in by_type or 'major_refactor' in by_type:
            total_lines = sum(c.lines_changed for c in changes)
            descriptions.append(f"Refactored {total_lines} lines across {len(changes)} file(s)")

        if descriptions:
            return "; ".join(descriptions)

        return f"Modified {len(changes)} file(s)"

    def consolidate_checkpoints(
        self,
        max_age_hours: int = 24,
        min_checkpoints_to_keep: int = 10,
        similarity_threshold: float = 0.8
    ) -> int:
        """Consolidate similar checkpoints to save space

        Args:
            max_age_hours: Only consolidate checkpoints older than this
            min_checkpoints_to_keep: Always keep at least this many checkpoints
            similarity_threshold: Similarity threshold for consolidation (0-1)

        Returns:
            Number of checkpoints consolidated
        """
        checkpoints = self.checkpoint_manager.list_checkpoints()

        if len(checkpoints) <= min_checkpoints_to_keep:
            logger.info("Not enough checkpoints to consolidate")
            return 0

        # Filter by age
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
        old_checkpoints = [
            cp for cp in checkpoints[min_checkpoints_to_keep:]
            if datetime.fromisoformat(cp.created_at) < cutoff_time
        ]

        if not old_checkpoints:
            logger.info("No old checkpoints to consolidate")
            return 0

        # Group similar checkpoints
        groups = self._group_similar_checkpoints(old_checkpoints, similarity_threshold)

        consolidated_count = 0

        # Consolidate each group (keep newest, delete others)
        for group in groups:
            if len(group) <= 1:
                continue

            # Sort by creation time
            group.sort(key=lambda cp: cp.created_at, reverse=True)

            # Keep the newest, delete others
            to_keep = group[0]
            to_delete = group[1:]

            for checkpoint in to_delete:
                try:
                    self.checkpoint_manager.delete_checkpoint(checkpoint.checkpoint_id)
                    consolidated_count += 1
                except Exception as e:
                    logger.warning(f"Failed to delete checkpoint {checkpoint.checkpoint_id}: {e}")

        logger.info(f"Consolidated {consolidated_count} checkpoint(s)")
        return consolidated_count

    def _group_similar_checkpoints(
        self,
        checkpoints: List[Checkpoint],
        threshold: float
    ) -> List[List[Checkpoint]]:
        """Group similar checkpoints together"""
        groups = []
        used = set()

        for i, cp1 in enumerate(checkpoints):
            if cp1.checkpoint_id in used:
                continue

            group = [cp1]
            used.add(cp1.checkpoint_id)

            # Find similar checkpoints
            for cp2 in checkpoints[i+1:]:
                if cp2.checkpoint_id in used:
                    continue

                similarity = self._calculate_checkpoint_similarity(cp1, cp2)
                if similarity >= threshold:
                    group.append(cp2)
                    used.add(cp2.checkpoint_id)

            groups.append(group)

        return groups

    def _calculate_checkpoint_similarity(
        self,
        cp1: Checkpoint,
        cp2: Checkpoint
    ) -> float:
        """Calculate similarity between two checkpoints (0-1)"""
        # Same operation type?
        type_match = 1.0 if cp1.operation_type == cp2.operation_type else 0.0

        # Overlapping files?
        files1 = set(s.file_path for s in cp1.snapshots)
        files2 = set(s.file_path for s in cp2.snapshots)

        if not files1 or not files2:
            file_overlap = 0.0
        else:
            intersection = len(files1 & files2)
            union = len(files1 | files2)
            file_overlap = intersection / union

        # Overlapping tags?
        tags1 = set(cp1.tags)
        tags2 = set(cp2.tags)

        if not tags1 or not tags2:
            tag_overlap = 0.0
        else:
            intersection = len(tags1 & tags2)
            union = len(tags1 | tags2)
            tag_overlap = intersection / union

        # Weighted average
        similarity = (0.3 * type_match + 0.4 * file_overlap + 0.3 * tag_overlap)

        return similarity

    def auto_checkpoint_if_needed(
        self,
        file_paths: List[str],
        old_contents: Dict[str, str],
        new_contents: Dict[str, str]
    ) -> Optional[Checkpoint]:
        """Automatically create checkpoint if changes warrant it

        Args:
            file_paths: Files that changed
            old_contents: Old file contents
            new_contents: New file contents

        Returns:
            Checkpoint if created, None otherwise
        """
        # Analyze changes
        all_changes = []
        for file_path in file_paths:
            old_content = old_contents.get(file_path, "")
            new_content = new_contents.get(file_path, "")

            if old_content or new_content:
                changes = self.semantic_analyzer.analyze_file_change(
                    file_path, old_content, new_content
                )
                all_changes.extend(changes)

        # Determine if checkpoint is needed
        needs_checkpoint = self._should_create_checkpoint(all_changes)

        if needs_checkpoint:
            return self.create_semantic_checkpoint(
                file_paths=file_paths,
                old_contents=old_contents,
                new_contents=new_contents
            )

        return None

    def _should_create_checkpoint(self, changes: List[CodeChange]) -> bool:
        """Determine if changes warrant an automatic checkpoint"""
        if not changes:
            return False

        # Always checkpoint refactorings
        refactoring_types = {
            'extract_function', 'extract_class',
            'rename_function', 'rename_class',
            'major_refactor'
        }

        if any(c.change_type in refactoring_types for c in changes):
            return True

        # Checkpoint if many lines changed
        total_lines = sum(c.lines_changed for c in changes)
        if total_lines > 50:
            return True

        # Checkpoint if many files changed
        if len(set(c.file_path for c in changes)) > 3:
            return True

        return False

"""
Code Intelligence Tools for poor-cli

Advanced code analysis and refactoring tools:
- AST analysis for Python/JavaScript
- Find references to symbols
- Extract function refactoring
- Rename symbol across codebase
- Dependency graph generation
- Code metrics
"""

import ast
import re
from pathlib import Path
from typing import List, Dict, Set, Optional, Any, Tuple
from dataclasses import dataclass, field
from collections import defaultdict

from poor_cli.exceptions import setup_logger

logger = setup_logger(__name__)


@dataclass
class Symbol:
    """Code symbol (function, class, variable)"""
    name: str
    symbol_type: str  # 'function', 'class', 'variable', 'import'
    file_path: str
    line_number: int
    column: int = 0
    scope: str = "global"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Reference:
    """Reference to a symbol"""
    symbol_name: str
    file_path: str
    line_number: int
    column: int
    context: str  # Surrounding code


@dataclass
class Dependency:
    """Module dependency"""
    from_module: str
    to_module: str
    import_type: str  # 'import', 'from_import'
    imported_names: List[str] = field(default_factory=list)


class PythonAnalyzer:
    """AST-based analysis for Python code"""

    def analyze_file(self, file_path: Path) -> Dict[str, Any]:
        """Analyze Python file

        Args:
            file_path: Path to Python file

        Returns:
            Analysis results
        """
        try:
            with open(file_path, 'r') as f:
                source = f.read()

            tree = ast.parse(source, filename=str(file_path))

            return {
                "symbols": self.extract_symbols(tree, str(file_path)),
                "dependencies": self.extract_dependencies(tree),
                "complexity": self.calculate_complexity(tree),
                "metrics": self.calculate_metrics(tree, source)
            }

        except Exception as e:
            logger.error(f"Failed to analyze {file_path}: {e}")
            return {}

    def extract_symbols(self, tree: ast.AST, file_path: str) -> List[Symbol]:
        """Extract all symbols from AST"""
        symbols = []

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                symbols.append(Symbol(
                    name=node.name,
                    symbol_type="function",
                    file_path=file_path,
                    line_number=node.lineno,
                    column=node.col_offset,
                    metadata={
                        "args": [arg.arg for arg in node.args.args],
                        "decorators": [self._get_decorator_name(d) for d in node.decorator_list]
                    }
                ))

            elif isinstance(node, ast.ClassDef):
                symbols.append(Symbol(
                    name=node.name,
                    symbol_type="class",
                    file_path=file_path,
                    line_number=node.lineno,
                    column=node.col_offset,
                    metadata={
                        "bases": [self._get_name(base) for base in node.bases],
                        "methods": [m.name for m in node.body if isinstance(m, ast.FunctionDef)]
                    }
                ))

            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        symbols.append(Symbol(
                            name=target.id,
                            symbol_type="variable",
                            file_path=file_path,
                            line_number=node.lineno,
                            column=node.col_offset
                        ))

        return symbols

    def extract_dependencies(self, tree: ast.AST) -> List[Dependency]:
        """Extract import dependencies"""
        dependencies = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    dependencies.append(Dependency(
                        from_module="__main__",
                        to_module=alias.name,
                        import_type="import",
                        imported_names=[alias.asname or alias.name]
                    ))

            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    dependencies.append(Dependency(
                        from_module="__main__",
                        to_module=node.module,
                        import_type="from_import",
                        imported_names=[alias.name for alias in node.names]
                    ))

        return dependencies

    def calculate_complexity(self, tree: ast.AST) -> Dict[str, int]:
        """Calculate cyclomatic complexity"""
        complexity = 0

        for node in ast.walk(tree):
            # Count decision points
            if isinstance(node, (ast.If, ast.While, ast.For, ast.ExceptHandler)):
                complexity += 1
            elif isinstance(node, ast.BoolOp):
                complexity += len(node.values) - 1

        return {
            "cyclomatic_complexity": complexity,
            "node_count": len(list(ast.walk(tree)))
        }

    def calculate_metrics(self, tree: ast.AST, source: str) -> Dict[str, Any]:
        """Calculate code metrics"""
        lines = source.split('\n')

        return {
            "total_lines": len(lines),
            "code_lines": len([l for l in lines if l.strip() and not l.strip().startswith('#')]),
            "comment_lines": len([l for l in lines if l.strip().startswith('#')]),
            "blank_lines": len([l for l in lines if not l.strip()]),
            "function_count": len([n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]),
            "class_count": len([n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)])
        }

    def _get_decorator_name(self, node: ast.AST) -> str:
        """Get decorator name from AST node"""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            return node.func.id
        return "unknown"

    def _get_name(self, node: ast.AST) -> str:
        """Get name from AST node"""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return f"{self._get_name(node.value)}.{node.attr}"
        return "unknown"


class ReferenceFinder:
    """Find all references to a symbol"""

    def find_references(
        self,
        symbol_name: str,
        workspace_root: Path,
        file_patterns: List[str] = None
    ) -> List[Reference]:
        """Find all references to a symbol

        Args:
            symbol_name: Symbol to find
            workspace_root: Root directory
            file_patterns: File patterns to search (e.g., ['*.py'])

        Returns:
            List of references
        """
        if file_patterns is None:
            file_patterns = ['*.py', '*.js', '*.ts', '*.tsx']

        references = []

        for pattern in file_patterns:
            for file_path in workspace_root.rglob(pattern):
                try:
                    refs = self._find_in_file(symbol_name, file_path)
                    references.extend(refs)
                except Exception as e:
                    logger.debug(f"Error searching {file_path}: {e}")

        logger.info(f"Found {len(references)} references to '{symbol_name}'")
        return references

    def _find_in_file(self, symbol_name: str, file_path: Path) -> List[Reference]:
        """Find references in a single file"""
        references = []

        try:
            with open(file_path, 'r') as f:
                lines = f.readlines()

            # Use word boundary regex
            pattern = re.compile(rf'\b{re.escape(symbol_name)}\b')

            for line_num, line in enumerate(lines, 1):
                matches = pattern.finditer(line)
                for match in matches:
                    references.append(Reference(
                        symbol_name=symbol_name,
                        file_path=str(file_path),
                        line_number=line_num,
                        column=match.start(),
                        context=line.strip()
                    ))

        except Exception as e:
            logger.debug(f"Error reading {file_path}: {e}")

        return references


class RefactoringTool:
    """Code refactoring tools"""

    def extract_function(
        self,
        file_path: Path,
        start_line: int,
        end_line: int,
        function_name: str
    ) -> Tuple[str, str]:
        """Extract code into a new function

        Args:
            file_path: File to refactor
            start_line: Start line of code to extract
            end_line: End line of code to extract
            function_name: Name for new function

        Returns:
            Tuple of (new_function, modified_file_content)
        """
        with open(file_path, 'r') as f:
            lines = f.readlines()

        # Extract code block
        extracted_lines = lines[start_line-1:end_line]
        extracted_code = ''.join(extracted_lines)

        # Determine indentation
        indent = len(extracted_lines[0]) - len(extracted_lines[0].lstrip())
        base_indent = ' ' * indent

        # Create new function
        new_function = f"def {function_name}():\n"
        for line in extracted_lines:
            new_function += f"    {line.lstrip()}"
        new_function += "\n\n"

        # Replace extracted code with function call
        call_line = f"{base_indent}{function_name}()\n"
        modified_lines = lines[:start_line-1] + [call_line] + lines[end_line:]

        # Insert function definition
        # Find good insertion point (after imports)
        insert_pos = 0
        for i, line in enumerate(modified_lines):
            if line.strip() and not line.strip().startswith(('import ', 'from ')):
                insert_pos = i
                break

        modified_lines.insert(insert_pos, new_function)

        modified_content = ''.join(modified_lines)

        return new_function, modified_content

    def rename_symbol(
        self,
        symbol_name: str,
        new_name: str,
        references: List[Reference]
    ) -> Dict[str, str]:
        """Rename symbol across all references

        Args:
            symbol_name: Current symbol name
            new_name: New symbol name
            references: List of references to rename

        Returns:
            Dict mapping file paths to modified content
        """
        # Group references by file
        by_file = defaultdict(list)
        for ref in references:
            by_file[ref.file_path].append(ref)

        modified_files = {}

        for file_path, file_refs in by_file.items():
            try:
                with open(file_path, 'r') as f:
                    content = f.read()

                # Sort references by position (reverse order to maintain positions)
                file_refs.sort(key=lambda r: (r.line_number, r.column), reverse=True)

                # Replace each reference
                lines = content.split('\n')
                for ref in file_refs:
                    line_idx = ref.line_number - 1
                    if 0 <= line_idx < len(lines):
                        line = lines[line_idx]
                        # Use word boundary replacement
                        pattern = re.compile(rf'\b{re.escape(symbol_name)}\b')
                        lines[line_idx] = pattern.sub(new_name, line, count=1)

                modified_content = '\n'.join(lines)
                modified_files[file_path] = modified_content

            except Exception as e:
                logger.error(f"Error renaming in {file_path}: {e}")

        logger.info(f"Renamed '{symbol_name}' to '{new_name}' in {len(modified_files)} files")
        return modified_files


class DependencyGraphBuilder:
    """Build dependency graphs"""

    def build_graph(
        self,
        workspace_root: Path,
        file_patterns: List[str] = None
    ) -> Dict[str, List[str]]:
        """Build dependency graph

        Args:
            workspace_root: Root directory
            file_patterns: File patterns to analyze

        Returns:
            Dict mapping modules to their dependencies
        """
        if file_patterns is None:
            file_patterns = ['*.py']

        graph = defaultdict(list)
        analyzer = PythonAnalyzer()

        for pattern in file_patterns:
            for file_path in workspace_root.rglob(pattern):
                try:
                    result = analyzer.analyze_file(file_path)
                    module_name = self._path_to_module(file_path, workspace_root)

                    for dep in result.get('dependencies', []):
                        graph[module_name].append(dep.to_module)

                except Exception as e:
                    logger.debug(f"Error analyzing {file_path}: {e}")

        return dict(graph)

    def find_circular_dependencies(self, graph: Dict[str, List[str]]) -> List[List[str]]:
        """Find circular dependencies

        Args:
            graph: Dependency graph

        Returns:
            List of circular dependency chains
        """
        cycles = []
        visited = set()

        def dfs(node: str, path: List[str]):
            if node in path:
                # Found cycle
                cycle_start = path.index(node)
                cycle = path[cycle_start:] + [node]
                if cycle not in cycles:
                    cycles.append(cycle)
                return

            if node in visited:
                return

            visited.add(node)
            path.append(node)

            for neighbor in graph.get(node, []):
                dfs(neighbor, path.copy())

        for node in graph:
            dfs(node, [])

        return cycles

    def _path_to_module(self, file_path: Path, workspace_root: Path) -> str:
        """Convert file path to module name"""
        relative = file_path.relative_to(workspace_root)
        parts = list(relative.parts)

        # Remove .py extension
        if parts[-1].endswith('.py'):
            parts[-1] = parts[-1][:-3]

        # Remove __init__
        if parts[-1] == '__init__':
            parts = parts[:-1]

        return '.'.join(parts)


class CodeIntelligence:
    """Main code intelligence interface"""

    def __init__(self, workspace_root: Optional[Path] = None):
        self.workspace_root = workspace_root or Path.cwd()
        self.python_analyzer = PythonAnalyzer()
        self.reference_finder = ReferenceFinder()
        self.refactoring_tool = RefactoringTool()
        self.dependency_builder = DependencyGraphBuilder()

    def analyze_file(self, file_path: Path) -> Dict[str, Any]:
        """Analyze file and return comprehensive results"""
        ext = file_path.suffix

        if ext == '.py':
            return self.python_analyzer.analyze_file(file_path)
        else:
            logger.warning(f"Unsupported file type: {ext}")
            return {}

    def find_all_references(self, symbol_name: str) -> List[Reference]:
        """Find all references to a symbol in workspace"""
        return self.reference_finder.find_references(
            symbol_name,
            self.workspace_root
        )

    def rename_symbol_everywhere(self, old_name: str, new_name: str) -> Dict[str, str]:
        """Rename symbol across entire workspace"""
        references = self.find_all_references(old_name)
        return self.refactoring_tool.rename_symbol(old_name, new_name, references)

    def get_dependency_graph(self) -> Dict[str, List[str]]:
        """Get dependency graph for workspace"""
        return self.dependency_builder.build_graph(self.workspace_root)

    def detect_circular_dependencies(self) -> List[List[str]]:
        """Detect circular dependencies in workspace"""
        graph = self.get_dependency_graph()
        return self.dependency_builder.find_circular_dependencies(graph)

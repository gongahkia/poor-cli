"""Code-specific tokenization research prototypes.
Approach A: pre-tokenization (whitespace/identifier normalization)
Approach B: hybrid AST-token representation
"""
import ast, re, textwrap
from pathlib import Path

# --- approach A: code pre-tokenization ---

def collapse_indentation(code: str, marker: str = "\t") -> str:
    """Replace leading spaces with tab markers. 4 spaces → 1 tab."""
    lines = []
    for line in code.splitlines():
        stripped = line.lstrip(" ")
        n_spaces = len(line) - len(stripped)
        indent = marker * (n_spaces // 4)
        remainder = " " * (n_spaces % 4)
        lines.append(indent + remainder + stripped)
    return "\n".join(lines)

def normalize_identifiers(code: str) -> str:
    """Convert camelCase identifiers to snake_case (BPE-friendlier).
    Only transforms identifiers, not string contents."""
    def camel_to_snake(match):
        name = match.group(0)
        if name.isupper() or "_" in name: return name # already CONST or snake
        result = re.sub(r'([A-Z]+)', lambda m: '_' + m.group(0).lower(), name)
        return result.lstrip('_')
    # match likely identifiers (not inside strings)
    return re.sub(r'\b[a-z][a-zA-Z0-9]{2,}\b', camel_to_snake, code)

def strip_comments_python(code: str) -> str:
    """Remove Python comments and docstrings."""
    lines = []
    in_docstring = False
    docstring_char = None
    for line in code.splitlines():
        stripped = line.strip()
        if in_docstring:
            if stripped.endswith(docstring_char) or docstring_char in stripped:
                in_docstring = False
            continue
        if stripped.startswith('"""') or stripped.startswith("'''"):
            docstring_char = stripped[:3]
            if stripped.count(docstring_char) >= 2: continue # single-line docstring
            in_docstring = True
            continue
        if "#" in line:
            code_part = line.split("#")[0].rstrip()
            if code_part: lines.append(code_part)
            continue
        if stripped: lines.append(line)
    return "\n".join(lines)

def strip_comments_lua(code: str) -> str:
    """Remove Lua single-line comments (-- ...)."""
    lines = []
    for line in code.splitlines():
        stripped = line.strip()
        if stripped.startswith("--"): continue
        if "--" in line:
            code_part = line.split("--")[0].rstrip()
            if code_part: lines.append(code_part)
            continue
        if stripped: lines.append(line)
    return "\n".join(lines)

def strip_comments_ts(code: str) -> str:
    """Remove TS/JS single-line comments (// ...)."""
    lines = []
    for line in code.splitlines():
        stripped = line.strip()
        if stripped.startswith("//"): continue
        if "//" in line:
            code_part = line.split("//")[0].rstrip()
            if code_part: lines.append(code_part)
            continue
        if stripped: lines.append(line)
    return "\n".join(lines)

def collapse_blank_lines(code: str) -> str:
    """Collapse multiple blank lines to single."""
    return re.sub(r'\n{3,}', '\n\n', code)

def pretokenize(code: str, lang: str = ".py") -> str:
    """Full pre-tokenization pipeline."""
    code = collapse_indentation(code)
    code = normalize_identifiers(code)
    if lang == ".py": code = strip_comments_python(code)
    elif lang == ".lua": code = strip_comments_lua(code)
    elif lang in (".ts", ".js", ".tsx"): code = strip_comments_ts(code)
    code = collapse_blank_lines(code)
    return code.strip()

# --- approach B: hybrid AST-token representation ---

def ast_compact_python(code: str) -> str | None:
    """Convert Python code to AST-compact representation.
    Returns None if AST parsing fails."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None
    lines = []
    _ast_node_to_compact(tree, lines, indent=0)
    return "\n".join(lines)

def _ast_node_to_compact(node, lines, indent):
    """Recursively convert AST nodes to compact representation."""
    prefix = "\t" * indent
    if isinstance(node, ast.Module):
        for child in ast.iter_child_nodes(node):
            _ast_node_to_compact(child, lines, indent)
    elif isinstance(node, ast.Import):
        names = ", ".join(a.name + (f" as {a.asname}" if a.asname else "") for a in node.names)
        lines.append(f"{prefix}import {names}")
    elif isinstance(node, ast.ImportFrom):
        names = ", ".join(a.name + (f" as {a.asname}" if a.asname else "") for a in node.names)
        lines.append(f"{prefix}from {node.module} import {names}")
    elif isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
        async_prefix = "async " if isinstance(node, ast.AsyncFunctionDef) else ""
        args = _compact_args(node.args)
        ret = ""
        if node.returns:
            ret = f" -> {ast.unparse(node.returns)}"
        decorators = "".join(f"{prefix}@{ast.unparse(d)}\n" for d in node.decorator_list)
        lines.append(f"{decorators}{prefix}{async_prefix}def {node.name}({args}){ret}:")
        for child in node.body:
            _ast_node_to_compact(child, lines, indent + 1)
    elif isinstance(node, ast.ClassDef):
        bases = ", ".join(ast.unparse(b) for b in node.bases)
        base_str = f"({bases})" if bases else ""
        decorators = "".join(f"{prefix}@{ast.unparse(d)}\n" for d in node.decorator_list)
        lines.append(f"{decorators}{prefix}class {node.name}{base_str}:")
        for child in node.body:
            _ast_node_to_compact(child, lines, indent + 1)
    elif isinstance(node, ast.Assign):
        targets = ", ".join(ast.unparse(t) for t in node.targets)
        lines.append(f"{prefix}{targets} = {ast.unparse(node.value)}")
    elif isinstance(node, ast.AnnAssign):
        target = ast.unparse(node.target)
        ann = ast.unparse(node.annotation)
        val = f" = {ast.unparse(node.value)}" if node.value else ""
        lines.append(f"{prefix}{target}: {ann}{val}")
    elif isinstance(node, ast.Return):
        val = f" {ast.unparse(node.value)}" if node.value else ""
        lines.append(f"{prefix}return{val}")
    elif isinstance(node, ast.Expr):
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            pass # skip docstrings
        else:
            lines.append(f"{prefix}{ast.unparse(node.value)}")
    elif isinstance(node, (ast.If, ast.For, ast.While, ast.With, ast.Try)):
        lines.append(f"{prefix}{ast.unparse(node).split(chr(10))[0]}") # first line only for header
        for child in ast.iter_child_nodes(node):
            if isinstance(child, list):
                for c in child:
                    _ast_node_to_compact(c, lines, indent + 1)
    else:
        try:
            unparsed = ast.unparse(node)
            if unparsed.strip():
                compact = " ".join(unparsed.split()) # collapse whitespace
                lines.append(f"{prefix}{compact}")
        except Exception:
            pass

def _compact_args(args) -> str:
    """Compact function arguments."""
    parts = []
    defaults_offset = len(args.args) - len(args.defaults)
    for i, arg in enumerate(args.args):
        s = arg.arg
        if arg.annotation: s += f": {ast.unparse(arg.annotation)}"
        di = i - defaults_offset
        if di >= 0 and di < len(args.defaults):
            s += f"={ast.unparse(args.defaults[di])}"
        parts.append(s)
    if args.vararg: parts.append(f"*{args.vararg.arg}")
    for i, arg in enumerate(args.kwonlyargs):
        s = arg.arg
        if arg.annotation: s += f": {ast.unparse(arg.annotation)}"
        if i < len(args.kw_defaults) and args.kw_defaults[i]:
            s += f"={ast.unparse(args.kw_defaults[i])}"
        parts.append(s)
    if args.kwarg: parts.append(f"**{args.kwarg.arg}")
    return ", ".join(parts)

# --- approach A+B combined: pretokenize then AST-compact ---

def pretokenize_ast(code: str, lang: str = ".py") -> str:
    """Apply pre-tokenization, then AST-compact for Python files."""
    if lang == ".py":
        compact = ast_compact_python(code)
        if compact: return compact
    return pretokenize(code, lang) # fallback

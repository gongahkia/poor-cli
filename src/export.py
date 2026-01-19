# src/export.py

"""Export grammars to various documentation formats."""


def export_to_latex(grammar):
    """Export grammar to LaTeX documentation format."""
    from .grammar import AbstractGrammar, ConcreteGrammar

    lines = []
    lines.append(r"\documentclass{article}")
    lines.append(r"\usepackage{amsmath}")
    lines.append(r"\usepackage{amssymb}")
    lines.append(r"\usepackage{booktabs}")
    lines.append(r"\begin{document}")
    lines.append("")

    if isinstance(grammar, AbstractGrammar):
        lines.append(r"\section*{Abstract Grammar: " + _latex_escape(grammar.name) + "}")
        lines.append("")

        # Categories
        lines.append(r"\subsection*{Categories}")
        lines.append(r"\begin{itemize}")
        for cat_name in sorted(grammar.categories.keys()):
            lines.append(r"  \item \texttt{" + _latex_escape(cat_name) + "}")
        lines.append(r"\end{itemize}")
        lines.append("")

        # Functions
        lines.append(r"\subsection*{Functions}")
        lines.append(r"\begin{align*}")
        for func in sorted(grammar.functions.values(), key=lambda f: f.name):
            args = " \\to ".join(f"\\text{{{_latex_escape(str(t))}}}" for t in func.arg_types)
            ret = f"\\text{{{_latex_escape(str(func.return_type))}}}"
            sig = f"{args} \\to {ret}" if args else ret
            lines.append(f"  \\text{{{_latex_escape(func.name)}}} &: {sig} \\\\")
        lines.append(r"\end{align*}")

    elif isinstance(grammar, ConcreteGrammar):
        lines.append(r"\section*{Concrete Grammar: " + _latex_escape(grammar.name) + "}")
        lines.append(r"\textbf{Implements:} \texttt{" + _latex_escape(grammar.abstract_name) + "}")
        lines.append("")

        # Linearization rules
        lines.append(r"\subsection*{Linearization Rules}")
        lines.append(r"\begin{tabular}{ll}")
        lines.append(r"\toprule")
        lines.append(r"\textbf{Function} & \textbf{Linearization} \\")
        lines.append(r"\midrule")
        for func_name, rule in sorted(grammar.linearization_rules.items()):
            body = " ++ ".join(rule.body_tokens)
            lines.append(f"\\texttt{{{_latex_escape(func_name)}}} & \\texttt{{{_latex_escape(body)}}} \\\\")
        lines.append(r"\bottomrule")
        lines.append(r"\end{tabular}")

    lines.append("")
    lines.append(r"\end{document}")

    return "\n".join(lines)


def export_to_html(grammar):
    """Export grammar to HTML documentation format."""
    from .grammar import AbstractGrammar, ConcreteGrammar

    lines = []
    lines.append("<!DOCTYPE html>")
    lines.append("<html lang='en'>")
    lines.append("<head>")
    lines.append("  <meta charset='UTF-8'>")
    lines.append("  <meta name='viewport' content='width=device-width, initial-scale=1.0'>")
    lines.append("  <title>Grammar Documentation</title>")
    lines.append("  <style>")
    lines.append("    body { font-family: system-ui, sans-serif; max-width: 800px; margin: 2rem auto; padding: 0 1rem; }")
    lines.append("    h1, h2 { color: #333; }")
    lines.append("    code { background: #f4f4f4; padding: 0.2em 0.4em; border-radius: 3px; }")
    lines.append("    table { border-collapse: collapse; width: 100%; margin: 1rem 0; }")
    lines.append("    th, td { border: 1px solid #ddd; padding: 0.5rem; text-align: left; }")
    lines.append("    th { background: #f8f8f8; }")
    lines.append("    .category { display: inline-block; background: #e3f2fd; padding: 0.2em 0.5em; margin: 0.2em; border-radius: 3px; }")
    lines.append("    .arrow { color: #666; }")
    lines.append("  </style>")
    lines.append("</head>")
    lines.append("<body>")

    if isinstance(grammar, AbstractGrammar):
        lines.append(f"  <h1>Abstract Grammar: {_html_escape(grammar.name)}</h1>")

        # Categories
        lines.append("  <h2>Categories</h2>")
        lines.append("  <div>")
        for cat_name in sorted(grammar.categories.keys()):
            lines.append(f"    <span class='category'>{_html_escape(cat_name)}</span>")
        lines.append("  </div>")

        # Functions
        lines.append("  <h2>Functions</h2>")
        lines.append("  <table>")
        lines.append("    <tr><th>Function</th><th>Signature</th></tr>")
        for func in sorted(grammar.functions.values(), key=lambda f: f.name):
            args = " <span class='arrow'>→</span> ".join(f"<code>{_html_escape(str(t))}</code>" for t in func.arg_types)
            ret = f"<code>{_html_escape(str(func.return_type))}</code>"
            sig = f"{args} <span class='arrow'>→</span> {ret}" if args else ret
            lines.append(f"    <tr><td><code>{_html_escape(func.name)}</code></td><td>{sig}</td></tr>")
        lines.append("  </table>")

        # Constraints
        if grammar.constraints:
            lines.append("  <h2>Constraints</h2>")
            lines.append("  <ul>")
            for func_name, constraint in grammar.constraints.items():
                for cat, values in constraint.requires.items():
                    lines.append(f"    <li><code>{_html_escape(func_name)}</code> requires {_html_escape(cat)} = {', '.join(values)}</li>")
            lines.append("  </ul>")

    elif isinstance(grammar, ConcreteGrammar):
        lines.append(f"  <h1>Concrete Grammar: {_html_escape(grammar.name)}</h1>")
        lines.append(f"  <p><strong>Implements:</strong> <code>{_html_escape(grammar.abstract_name)}</code></p>")

        # Linearization rules
        lines.append("  <h2>Linearization Rules</h2>")
        lines.append("  <table>")
        lines.append("    <tr><th>Function</th><th>Linearization</th></tr>")
        for func_name, rule in sorted(grammar.linearization_rules.items()):
            body = " ++ ".join(rule.body_tokens)
            lines.append(f"    <tr><td><code>{_html_escape(func_name)}</code></td><td><code>{_html_escape(body)}</code></td></tr>")
        lines.append("  </table>")

    lines.append("</body>")
    lines.append("</html>")

    return "\n".join(lines)


def _latex_escape(text):
    """Escape special LaTeX characters."""
    replacements = [
        ('\\', r'\textbackslash{}'),
        ('&', r'\&'),
        ('%', r'\%'),
        ('$', r'\$'),
        ('#', r'\#'),
        ('_', r'\_'),
        ('{', r'\{'),
        ('}', r'\}'),
        ('~', r'\textasciitilde{}'),
        ('^', r'\textasciicircum{}'),
    ]
    for old, new in replacements:
        text = text.replace(old, new)
    return text


def _html_escape(text):
    """Escape special HTML characters."""
    return (text
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;')
            .replace("'", '&#39;'))

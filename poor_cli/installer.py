"""Interactive CLI installer for poor-cli, inspired by mo's onboarding TUI."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

from poor_cli import __version__

LOGO = r"""
                                      ___
  _ __    ___    ___   _ __          / __\ |  (_)
 | '_ \  / _ \  / _ \ | '__|  ____ | |    | |  _
 | |_) || (_) || (_) || |    |____|| |___ | | | |
 | .__/  \___/  \___/ |_|          \____/ |_| |_|
 |_|
"""

TAGLINE = "AI coding assistant — multi-provider, multi-surface"

MENU_ITEMS = [
    ("Install / Update", "install or upgrade poor-cli and dependencies"),
    ("Configure Providers", "set up API keys for Gemini, OpenAI, Claude, Ollama"),
    ("Setup Telegram Bot", "guided Telegram bot token and launch configuration"),
    ("Build TUI", "compile the Rust terminal UI from source"),
    ("System Check", "verify installation, providers, and environment"),
    ("Uninstall", "remove poor-cli and its data"),
]

# -- ansi helpers --

def _dim(text: str) -> str:
    return f"\033[2m{text}\033[0m"

def _bold(text: str) -> str:
    return f"\033[1m{text}\033[0m"

def _green(text: str) -> str:
    return f"\033[32m{text}\033[0m"

def _yellow(text: str) -> str:
    return f"\033[33m{text}\033[0m"

def _red(text: str) -> str:
    return f"\033[31m{text}\033[0m"

def _cyan(text: str) -> str:
    return f"\033[36m{text}\033[0m"

def _magenta(text: str) -> str:
    return f"\033[35m{text}\033[0m"

def _bg_green(text: str) -> str:
    return f"\033[42;30m{text}\033[0m"

def _bg_yellow(text: str) -> str:
    return f"\033[43;30m{text}\033[0m"

def _bg_red(text: str) -> str:
    return f"\033[41;37m{text}\033[0m"

def _clear() -> None:
    os.system("cls" if os.name == "nt" else "clear")

# -- dashboard rendering primitives --

BAR_FULL = "█"
BAR_MED = "▓"
BAR_LOW = "░"

def _bar(fraction: float, width: int = 16, color_fn=None) -> str:
    """render a progress bar like ████████░░░░░░░░."""
    fraction = max(0.0, min(1.0, fraction))
    filled = round(fraction * width)
    empty = width - filled
    if color_fn is None:
        if fraction >= 0.7:
            color_fn = _green
        elif fraction >= 0.3:
            color_fn = _yellow
        else:
            color_fn = _red
    return color_fn(BAR_FULL * filled) + _dim(BAR_LOW * empty)

def _bar_ok(ok: bool, width: int = 10) -> str:
    """binary bar: full green or full red."""
    if ok:
        return _green(BAR_FULL * width)
    return _red(BAR_LOW * width)

def _health_score(checks: list[bool]) -> int:
    """compute 0-100 health score from boolean checks."""
    if not checks:
        return 0
    return round(sum(checks) / len(checks) * 100)

def _health_color(score: int) -> str:
    if score >= 80:
        return _bg_green(f" Health ● {score} ")
    elif score >= 50:
        return _bg_yellow(f" Health ● {score} ")
    return _bg_red(f" Health ● {score} ")

def _section_header(icon: str, title: str) -> str:
    return f"  {icon} {_bold(title)}"

def _row(label: str, bar: str, value: str, label_w: int = 14) -> str:
    return f"  {label:<{label_w}}{bar}  {value}"

def _get_term_width() -> int:
    try:
        return os.get_terminal_size().columns
    except OSError:
        return 80

def _side_by_side(left_lines: list[str], right_lines: list[str], col_width: int = 38, gutter: int = 4) -> list[str]:
    """merge two columns into side-by-side output."""
    max_rows = max(len(left_lines), len(right_lines))
    pad_l = [l if i < len(left_lines) else "" for i, l in enumerate(left_lines + [""] * max_rows)]
    pad_r = [r if i < len(right_lines) else "" for i, r in enumerate(right_lines + [""] * max_rows)]
    out = []
    for l, r in zip(pad_l[:max_rows], pad_r[:max_rows]):
        # strip ansi for width calc
        raw_l = _strip_ansi(l)
        padding = col_width - len(raw_l)
        if padding < 0:
            padding = 0
        out.append(l + " " * padding + " " * gutter + r)
    return out

def _strip_ansi(s: str) -> str:
    import re
    return re.sub(r"\033\[[0-9;]*m", "", s)

def _prompt(msg: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        val = input(f"  {msg}{suffix}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return default
    return val or default

def _confirm(msg: str, default: bool = True) -> bool:
    hint = "Y/n" if default else "y/N"
    try:
        val = input(f"  {msg} ({hint}): ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return default
    if not val:
        return default
    return val in ("y", "yes")

def _run(cmd: list[str], check: bool = True, capture: bool = False) -> subprocess.CompletedProcess:
    print(f"  {_dim('$')} {_dim(' '.join(cmd))}")
    return subprocess.run(cmd, check=check, capture_output=capture, text=True)

def _check_mark(ok: bool) -> str:
    return _green("✓") if ok else _red("✗")

def _has_command(name: str) -> bool:
    return shutil.which(name) is not None

def _press_enter() -> None:
    try:
        input(f"\n  {_dim('press enter to continue...')}")
    except (EOFError, KeyboardInterrupt):
        pass

def _read_key() -> str:
    """read single keypress, decode arrow escape seqs."""
    if os.name == "nt":
        import msvcrt
        ch = msvcrt.getwch()
        if ch in ('\x00', '\xe0'):
            ch2 = msvcrt.getwch()
            return {'H': 'up', 'P': 'down'}.get(ch2, '')
        return ch
    import tty, termios
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch == '\x1b':
            ch2 = sys.stdin.read(1)
            if ch2 == '[':
                ch3 = sys.stdin.read(1)
                return {'A': 'up', 'B': 'down'}.get(ch3, '')
            return 'esc'
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)

def _select(items: list[tuple[str, str]], allow_quit: bool = False, label_w: int = 24) -> int:
    """arrow-key/hjkl menu. returns selected index or -1 for quit/back."""
    if not sys.stdin.isatty(): # fallback for non-tty
        for i, (label, desc) in enumerate(items):
            print(f"    {i + 1}. {label:<{label_w}}{_dim(desc)}")
        choice = _prompt("choice", "1")
        if choice.lower() in ("q", "quit"):
            return -1
        try:
            idx = int(choice) - 1
            return idx if 0 <= idx < len(items) else -1
        except ValueError:
            return -1
    sel, n = 0, len(items)
    hint_parts = ["↑↓/jk navigate", "enter select"]
    if allow_quit:
        hint_parts.append("q quit")
    hint = " · ".join(hint_parts)
    total = n + 2 # items + blank + hint
    first = True
    while True:
        if not first:
            sys.stdout.write(f"\033[{total}A")
        first = False
        for i, (label, desc) in enumerate(items):
            marker = _cyan("›") if i == sel else " "
            num = f"{i + 1}."
            if i == sel:
                line = f"  {marker} {_bold(num)} {_bold(f'{label:<{label_w}}')}{desc}"
            else:
                line = f"  {marker} {num} {f'{label:<{label_w}}'}{_dim(desc)}"
            sys.stdout.write(f"\033[K{line}\n")
        sys.stdout.write(f"\033[K\n\033[K  {_dim(hint)}\n")
        sys.stdout.flush()
        key = _read_key()
        if key in ('up', 'k'):
            sel = (sel - 1) % n
        elif key in ('down', 'j'):
            sel = (sel + 1) % n
        elif key in ('\r', '\n'):
            return sel
        elif key in ('q', 'Q') and allow_quit:
            return -1
        elif key == '\x03': # ctrl-c
            return -1

# -- screens --

def _render_banner() -> None:
    _clear()
    print(_cyan(LOGO))
    print(f"  {_bold(TAGLINE)}")
    print(f"  {_dim(f'v{__version__}  •  https://github.com/gongahkia/poor-cli')}")
    print(f"  {_dim('─' * 52)}\n")

def show_landing() -> int:
    """Main installer entry point. Returns exit code."""
    handlers = [
        _handle_install,
        _handle_configure_providers,
        _handle_telegram_setup,
        _handle_build_tui,
        _handle_system_check,
        _handle_uninstall,
    ]
    while True:
        _render_banner()
        idx = _select(MENU_ITEMS, allow_quit=True)
        if idx < 0:
            print(f"\n  {_dim('bye!')}\n")
            return 0
        handlers[idx]()

# -- 1. install / update --

def _handle_install() -> None:
    _render_banner()
    print(f"  {_bold('install / update poor-cli')}\n")
    methods = [
        ("pip (recommended)", "pip install --upgrade poor-cli"),
        ("pip with all extras", "pip install --upgrade 'poor-cli[all]'"),
        ("from source (dev)", "pip install -e '.[all]'"),
    ]
    idx = _select(methods, allow_quit=True, label_w=28)
    if idx < 0:
        return
    _, cmd = methods[idx]
    print()
    if idx == 2: # source install
        repo_root = Path(__file__).resolve().parent.parent
        _run([sys.executable, "-m", "pip", "install", "-e", f"{repo_root}[all]"], check=False)
    else:
        parts = cmd.split()
        _run([sys.executable, "-m", *parts], check=False)
    # install shell completions
    if _confirm("install shell completions?"):
        _install_completions()
    _press_enter()

def _install_completions() -> None:
    completions_dir = Path(__file__).resolve().parent.parent / "completions"
    shell = os.environ.get("SHELL", "")
    if "zsh" in shell:
        src = completions_dir / "_poor-cli"
        if src.is_file():
            dest = Path.home() / ".zfunc" / "_poor-cli"
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            print(f"  {_green('✓')} zsh completion -> {dest}")
            print(f"  {_dim('add to .zshrc: fpath=(~/.zfunc $fpath) && autoload -Uz compinit && compinit')}")
        else:
            print(f"  {_yellow('!')} zsh completion file not found at {src}")
    elif "bash" in shell:
        src = completions_dir / "poor-cli.bash"
        if src.is_file():
            dest = Path.home() / ".local" / "share" / "bash-completion" / "completions" / "poor-cli"
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            print(f"  {_green('✓')} bash completion -> {dest}")
        else:
            print(f"  {_yellow('!')} bash completion file not found at {src}")
    elif "fish" in shell:
        src = completions_dir / "poor-cli.fish"
        if src.is_file():
            dest = Path.home() / ".config" / "fish" / "completions" / "poor-cli.fish"
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            print(f"  {_green('✓')} fish completion -> {dest}")
        else:
            print(f"  {_yellow('!')} fish completion file not found at {src}")
    else:
        print(f"  {_yellow('!')} shell not detected, skipping completions")

# -- 2. configure providers --

def _handle_configure_providers() -> None:
    from poor_cli.provider_catalog import provider_catalog
    catalog = provider_catalog()
    _render_banner()
    print(f"  {_bold('configure AI providers')}\n")
    print(f"  {_dim('poor-cli supports multiple providers. configure API keys below.')}")
    print(f"  {_dim('keys are stored encrypted in ~/.poor-cli/keys/')}\n")
    providers = list(catalog.values())
    provider_items = []
    for entry in providers:
        env_val = os.environ.get(entry.env_var, "")
        status = "configured" if env_val else "not set"
        provider_items.append((entry.display_name, f"{entry.env_var:<30} {status}"))
    idx = _select(provider_items, allow_quit=True, label_w=16)
    if idx < 0:
        return
    entry = providers[idx]
    print()
    print(f"  {_bold(entry.display_name)}")
    print(f"  {entry.setup_help}")
    print(f"  {_dim(f'capabilities: {entry.capability_summary}')}")
    print(f"  {_dim(f'default model: {entry.default_model}')}")
    print(f"  {_dim(f'models: {", ".join(entry.common_models)}')}")
    print()
    if entry.name == "ollama":
        _configure_ollama()
    else:
        _configure_cloud_provider(entry)
    _press_enter()

def _configure_cloud_provider(entry) -> None:
    current = os.environ.get(entry.env_var, "")
    if current:
        masked = current[:8] + "..." + current[-4:] if len(current) > 16 else "***"
        print(f"  current: {masked}")
        if not _confirm("replace existing key?", default=False):
            return
    key = _prompt(f"paste {entry.display_name} API key (or empty to skip)")
    if not key:
        return
    # save to encrypted store
    try:
        from poor_cli.api_key_manager import get_api_key_manager
        mgr = get_api_key_manager()
        mgr.store_key(entry.name, key)
        print(f"  {_green('✓')} key saved to encrypted store")
    except Exception as e:
        print(f"  {_yellow('!')} encrypted store failed ({e}), falling back to env var")
    # offer to add to shell profile
    shell = os.environ.get("SHELL", "")
    profile = None
    if "zsh" in shell:
        profile = Path.home() / ".zshrc"
    elif "bash" in shell:
        profile = Path.home() / ".bashrc"
    if profile and _confirm(f"add export to {profile.name}?"):
        line = f'\nexport {entry.env_var}="{key}"\n'
        with open(profile, "a") as f:
            f.write(line)
        print(f"  {_green('✓')} added to {profile}")
        print(f"  {_dim('run: source ' + str(profile))}")
    # also set in current process so system check works
    os.environ[entry.env_var] = key

def _configure_ollama() -> None:
    if _has_command("ollama"):
        print(f"  {_green('✓')} ollama binary found")
        result = _run(["ollama", "list"], check=False, capture=True)
        if result.returncode == 0:
            lines = result.stdout.strip().split("\n")
            print(f"  {_green('✓')} ollama running, {len(lines) - 1} model(s)")
            for line in lines[:6]:
                print(f"    {_dim(line)}")
            if len(lines) > 6:
                print(f"    {_dim(f'... and {len(lines) - 6} more')}")
        else:
            print(f"  {_yellow('!')} ollama not running")
            if _confirm("start ollama?"):
                _run(["ollama", "serve"], check=False)
    else:
        print(f"  {_red('✗')} ollama not found")
        print(f"  {_dim('install: https://ollama.com/download')}")
        if sys.platform == "darwin" and _has_command("brew"):
            if _confirm("install via homebrew?"):
                _run(["brew", "install", "ollama"], check=False)

# -- 3. telegram setup --

def _handle_telegram_setup() -> None:
    _render_banner()
    print(f"  {_bold('telegram bot setup')}\n")
    print("  step 1: create a bot")
    print(f"    {_dim('open Telegram and search for @BotFather')}")
    print(f"    {_dim('send /newbot and follow the prompts')}")
    print(f"    {_dim('copy the token (format: 123456:ABC-DEF...)')}")
    print()
    token = os.environ.get("POOR_CLI_TELEGRAM_TOKEN", "")
    if token:
        masked = token[:8] + "..." + token[-4:] if len(token) > 16 else "***"
        print(f"  {_green('✓')} POOR_CLI_TELEGRAM_TOKEN already set: {masked}")
        if not _confirm("replace?", default=False):
            token_final = token
        else:
            token_final = _prompt("paste bot token")
    else:
        token_final = _prompt("paste bot token (or empty to skip)")
    if not token_final:
        _press_enter()
        return
    # validate format
    import re
    if not re.match(r"^\d+:[A-Za-z0-9_-]{30,}$", token_final):
        print(f"  {_red('✗')} token format looks invalid (expected <bot_id>:<hash>)")
        _press_enter()
        return
    # save to env
    os.environ["POOR_CLI_TELEGRAM_TOKEN"] = token_final
    shell = os.environ.get("SHELL", "")
    profile = None
    if "zsh" in shell:
        profile = Path.home() / ".zshrc"
    elif "bash" in shell:
        profile = Path.home() / ".bashrc"
    if profile and _confirm(f"add export to {profile.name}?"):
        line = f'\nexport POOR_CLI_TELEGRAM_TOKEN="{token_final}"\n'
        with open(profile, "a") as f:
            f.write(line)
        print(f"  {_green('✓')} token saved to {profile}")
    print()
    print("  step 2: optional settings")
    allowed = _prompt("allowed user IDs (comma-separated, or empty for all)")
    sandbox = _prompt("sandbox preset", "review-only")
    print()
    print(f"  {_bold('ready! launch with:')}")
    cmd = "poor-cli telegram"
    if allowed:
        cmd += f" --allowed-users {allowed}"
    if sandbox != "review-only":
        cmd += f" --sandbox-preset {sandbox}"
    cmd += " --verbose"
    print(f"  {_cyan(cmd)}")
    print()
    if _confirm("launch now?"):
        print()
        os.execvp(sys.executable, [sys.executable, "-m", "poor_cli", "telegram",
                                    "--token", token_final,
                                    *(["--allowed-users", allowed] if allowed else []),
                                    "--sandbox-preset", sandbox,
                                    "--verbose"])
    _press_enter()

# -- 4. build TUI --

def _handle_build_tui() -> None:
    _render_banner()
    print(f"  {_bold('build Rust TUI')}\n")
    if not _has_command("cargo"):
        print(f"  {_red('✗')} cargo not found")
        print(f"  {_dim('install Rust: https://rustup.rs')}")
        if sys.platform == "darwin" and _has_command("brew"):
            if _confirm("install via homebrew?"):
                _run(["brew", "install", "rust"], check=False)
            else:
                _press_enter()
                return
        else:
            _press_enter()
            return
    tui_dir = Path(__file__).resolve().parent.parent / "poor-cli-tui"
    if not tui_dir.is_dir():
        print(f"  {_red('✗')} poor-cli-tui/ directory not found")
        print(f"  {_dim('this is only available in a git clone, not a pip install')}")
        _press_enter()
        return
    print(f"  {_green('✓')} cargo found")
    print(f"  {_green('✓')} TUI source found at {tui_dir}")
    print()
    if _confirm("build release binary?"):
        result = _run(["cargo", "build", "--release", "--manifest-path", str(tui_dir / "Cargo.toml")], check=False)
        if result.returncode == 0:
            binary = tui_dir / "target" / "release" / ("poor-cli-tui.exe" if os.name == "nt" else "poor-cli-tui")
            print(f"\n  {_green('✓')} built: {binary}")
            if _confirm("add to PATH via symlink?"):
                link = Path.home() / ".local" / "bin" / "poor-cli-tui"
                link.parent.mkdir(parents=True, exist_ok=True)
                if link.exists() or link.is_symlink():
                    link.unlink()
                link.symlink_to(binary)
                print(f"  {_green('✓')} symlinked: {link} -> {binary}")
                print(f"  {_dim('ensure ~/.local/bin is in your PATH')}")
        else:
            print(f"\n  {_red('✗')} build failed (exit {result.returncode})")
    _press_enter()

# -- 5. system check (mo-style dashboard) --

def _gather_provider_status() -> list[dict]:
    """probe all providers and return status dicts."""
    from poor_cli.provider_catalog import provider_catalog
    catalog = provider_catalog()
    results = []
    for name, entry in catalog.items():
        ok = False
        detail = ""
        if name == "ollama":
            ok = _has_command("ollama")
            if ok:
                try:
                    r = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=5)
                    if r.returncode == 0:
                        n = max(0, len(r.stdout.strip().split("\n")) - 1)
                        detail = f"{n} model{'s' if n != 1 else ''}"
                    else:
                        detail = "not running"
                        ok = False
                except Exception:
                    detail = "timeout"
                    ok = False
            else:
                detail = "not installed"
        else:
            env_val = os.environ.get(entry.env_var, "")
            ok = bool(env_val)
            if not ok:
                try:
                    from poor_cli.api_key_manager import get_api_key_manager
                    mgr = get_api_key_manager()
                    stored = mgr.get_key(name)
                    ok = bool(stored)
                except Exception:
                    pass
            detail = "configured" if ok else "no key"
        results.append({"name": entry.display_name, "ok": ok, "detail": detail,
                        "default_model": entry.default_model})
    return results

def _gather_storage_info() -> dict:
    """collect ~/.poor-cli storage stats."""
    config_dir = Path.home() / ".poor-cli"
    info: dict = {"config_dir": str(config_dir), "exists": config_dir.is_dir(),
                  "keys": 0, "sessions_kb": 0, "telegram_kb": 0, "audit_kb": 0, "total_kb": 0}
    if not config_dir.is_dir():
        return info
    keys_dir = config_dir / "keys"
    if keys_dir.is_dir():
        info["keys"] = len(list(keys_dir.glob("*.json")))
    for fname, key in [("telegram.db", "telegram_kb"), ("sessions", "sessions_kb"), ("audit", "audit_kb")]:
        p = config_dir / fname
        if p.is_file():
            info[key] = p.stat().st_size / 1024
        elif p.is_dir():
            info[key] = sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) / 1024
    total = 0
    for f in config_dir.rglob("*"):
        if f.is_file():
            total += f.stat().st_size
    info["total_kb"] = total / 1024
    return info

def _gather_deps_status() -> list[dict]:
    """check optional and core package availability."""
    deps = []
    for mod, label, required in [
        ("google.genai", "google-genai", True),
        ("openai", "openai", True),
        ("rich", "rich", True),
        ("yaml", "PyYAML", True),
        ("pydantic", "pydantic", True),
        ("cryptography", "cryptography", True),
        ("anthropic", "anthropic", False),
        ("telegram", "telegram-bot", False),
    ]:
        try:
            __import__(mod)
            deps.append({"name": label, "ok": True, "required": required})
        except ImportError:
            deps.append({"name": label, "ok": False, "required": required})
    return deps

def _handle_system_check() -> None:
    _clear()
    # -- gather all data first --
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    py_ok = sys.version_info >= (3, 11)
    providers = _gather_provider_status()
    storage = _gather_storage_info()
    deps = _gather_deps_status()
    tools_list = ["git", "cargo", "node", "gh", "docker", "ollama"]
    tools_ok = {t: _has_command(t) for t in tools_list}
    from poor_cli.tui_launcher import resolve_tui_binary
    tui_bin, tui_src = resolve_tui_binary()
    # health checks
    checks = [
        py_ok,
        *[p["ok"] for p in providers],
        storage["exists"],
        *[d["ok"] for d in deps if d["required"]],
        tools_ok["git"],
        tui_bin is not None,
    ]
    score = _health_score(checks)
    prov_ready = sum(1 for p in providers if p["ok"])
    # -- status bar --
    machine_info = f"{platform.node()}  ·  {platform.machine()}"
    if sys.platform == "darwin":
        machine_info = f"macOS {platform.mac_ver()[0]}  ·  {platform.machine()}"
    elif sys.platform.startswith("linux"):
        machine_info = f"Linux  ·  {platform.machine()}"
    print()
    print(f"  {_bold('Status')}  {_health_color(score)}  {machine_info}  ·  Python {py_ver}  ·  poor-cli {__version__}")
    print(f"  {_dim('─' * 72)}")
    print()
    # -- left column: providers + storage --
    left = []
    left.append(_section_header(_green("◉"), "Providers"))
    for p in providers:
        left.append(_row(p["name"], _bar_ok(p["ok"]), f'{p["detail"]}'))
    left.append(f"  {'Ready':<14}{_bar(prov_ready / max(len(providers), 1))}  {prov_ready}/{len(providers)}")
    left.append("")
    left.append(_section_header(_cyan("◧"), "Storage"))
    config_dir = Path.home() / ".poor-cli"
    left.append(f"  {'Path':<14}{_dim(str(config_dir))}")
    if storage["exists"]:
        total_kb = storage["total_kb"]
        total_str = f"{total_kb:.0f} KB" if total_kb < 1024 else f"{total_kb / 1024:.1f} MB"
        cap_kb = 512 * 1024 # 500MB soft cap for bar viz
        left.append(_row("Total", _bar(max(0.05, min(total_kb / cap_kb, 1.0)), color_fn=_cyan), total_str))
        left.append(_row("Keys", _bar_ok(storage["keys"] > 0, width=10), f'{storage["keys"]} stored'))
        if storage["telegram_kb"] > 0:
            left.append(_row("Telegram DB", _bar(min(storage["telegram_kb"] / 1024, 1.0), color_fn=_cyan), f'{storage["telegram_kb"]:.0f} KB'))
        if storage["audit_kb"] > 0:
            left.append(_row("Audit", _bar(min(storage["audit_kb"] / 1024, 1.0), color_fn=_cyan), f'{storage["audit_kb"]:.0f} KB'))
    else:
        left.append(f"  {_yellow('not initialized')}  {_dim('run poor-cli to create')}")
    # -- right column: deps + tools --
    right = []
    right.append(_section_header(_yellow("◈"), "Packages"))
    core_ok = sum(1 for d in deps if d["required"] and d["ok"])
    core_total = sum(1 for d in deps if d["required"])
    opt_ok = sum(1 for d in deps if not d["required"] and d["ok"])
    opt_total = sum(1 for d in deps if not d["required"])
    right.append(f"  {'Core':<14}{_bar(core_ok / max(core_total, 1))}  {core_ok}/{core_total}")
    right.append(f"  {'Optional':<14}{_bar(opt_ok / max(opt_total, 1))}  {opt_ok}/{opt_total}")
    for d in deps:
        tag = "" if d["required"] else _dim(" (opt)")
        dname = d["name"][:13]
        right.append(_row(dname, _bar_ok(d["ok"], width=10), (_green("ok") if d["ok"] else _dim("missing")) + tag))
    right.append("")
    right.append(_section_header(_magenta("⚙"), "Tools"))
    for t in tools_list:
        ok = tools_ok[t]
        right.append(_row(t, _bar_ok(ok, width=10), _green("found") if ok else _dim("missing")))
    right.append("")
    right.append(_section_header(_green("▣"), "TUI"))
    if tui_bin:
        right.append(f"  {'Binary':<14}{_bar_ok(True, width=10)}  {_green(tui_src or 'found')}")
        path_str = str(tui_bin)
        if len(path_str) > 36:
            path_str = "..." + path_str[-33:]
        right.append(f"  {'Path':<14}{_dim(path_str)}")
    else:
        right.append(f"  {'Binary':<14}{_bar_ok(False, width=10)}  {_dim('not found')}")
    # -- render side by side --
    tw = _get_term_width()
    if tw >= 84:
        for line in _side_by_side(left, right, col_width=40, gutter=2):
            print(line)
    else: # narrow terminal: stack vertically
        for line in left:
            print(line)
        print()
        for line in right:
            print(line)
    # -- footer --
    print(f"\n  {_dim('─' * 72)}")
    issues = []
    for p in providers:
        if not p["ok"]:
            issues.append(f"provider {p['name']} not configured")
    for d in deps:
        if d["required"] and not d["ok"]:
            issues.append(f"missing core package: {d['name']}")
    if not tui_bin:
        issues.append("TUI binary not found (optional)")
    if issues:
        print(f"  {_yellow('!')} {len(issues)} issue{'s' if len(issues) != 1 else ''}:")
        for issue in issues[:5]:
            print(f"    {_dim('·')} {issue}")
    else:
        print(f"  {_green('✓')} all checks passed")
    _press_enter()

# -- 6. uninstall --

def _handle_uninstall() -> None:
    _render_banner()
    print(f"  {_bold('uninstall poor-cli')}\n")
    print(f"  {_yellow('!')} this will:")
    print(f"    • pip uninstall poor-cli")
    print(f"    • optionally remove ~/.poor-cli/ (config, keys, sessions)")
    print()
    if not _confirm("proceed?", default=False):
        return
    _run([sys.executable, "-m", "pip", "uninstall", "poor-cli", "-y"], check=False)
    config_dir = Path.home() / ".poor-cli"
    if config_dir.is_dir():
        if _confirm(f"remove {config_dir}/ (config, encrypted keys, sessions)?", default=False):
            import shutil as _shutil
            _shutil.rmtree(config_dir)
            print(f"  {_green('✓')} removed {config_dir}")
        else:
            print(f"  {_dim('kept')} {config_dir}")
    print(f"\n  {_dim('note: remove POOR_CLI_TELEGRAM_TOKEN and API key exports from your shell profile manually')}")
    _press_enter()

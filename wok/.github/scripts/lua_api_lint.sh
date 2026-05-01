#!/usr/bin/env bash
# Lint docs/wok.d.lua for missing ---@since annotations.
#
# Every public surface (top-level ---@class wok.X, every `function wok.x.y(...)`
# declaration, the wok global itself) must have an `---@since X.Y.Z` line in
# the doc block immediately preceding the declaration. The doc block is the
# contiguous run of `---` lines (and bare `--` continuations) that ends at a
# blank line or non-doc code line.
#
# Exit 0 if every declaration is annotated; non-zero with a list of offenders
# otherwise. Run from the repo root:
#
#   .github/scripts/lua_api_lint.sh
#
# Skipped intentionally:
#   - `local wok = {}`           — wok itself is the global; the wok class
#                                  declaration covers it.
#   - `wok.X = {}`               — namespace-table assignments aren't typed
#                                  surfaces; the function declarations under
#                                  them are what carry @since.
#   - `---@alias`                — LuaCATS does not currently support
#                                  since-tagging type aliases.
#
# Pure awk; no python, no jq. Portable to macOS / Linux runners.

set -euo pipefail

FILE="${1:-docs/wok.d.lua}"

if [[ ! -f "$FILE" ]]; then
    echo "lua_api_lint: file not found: $FILE" >&2
    exit 2
fi

violations="$(awk '
    function check_block(decl_kind, decl_line, decl_text) {
        had_since = 0
        for (i = 0; i < n_doc; i++) {
            if (doc_block[i] ~ /---@since[[:space:]]+[0-9]+\.[0-9]+\.[0-9]+/) {
                had_since = 1
                break
            }
        }
        if (!had_since) {
            printf("MISSING:%s:%d:%s\n", decl_kind, decl_line, decl_text)
        }
    }

    # End of doc-collection: blank line OR a code line that does not start
    # with --- (e.g. `function wok.x.y() end` or `wok.X = {}`).
    function flush_doc_block() {
        # If the doc block opened with `---@class wok.X`, the class line is
        # itself the declaration we validate. Otherwise the next code line
        # decides what is being declared.
        if (n_doc > 0 && doc_block[0] ~ /^---@class[[:space:]]+wok(\.|[[:space:]]|$)/) {
            check_block("class", first_doc_line, doc_block[0])
        }
        n_doc = 0
        first_doc_line = 0
    }

    # Collect every doc line (--- or bare --) into doc_block.
    /^---/ || /^--[^!]/ {
        if (n_doc == 0) first_doc_line = NR
        doc_block[n_doc++] = $0
        next
    }

    # Blank line: ends the current doc block.
    /^[[:space:]]*$/ {
        flush_doc_block()
        next
    }

    # Function declaration on a public wok.* surface: validate against the
    # doc block we just collected, then drop it.
    /^function[[:space:]]+wok\./ {
        check_block("function", NR, $0)
        n_doc = 0
        first_doc_line = 0
        next
    }

    # Any other code line ends the doc block too. Class declarations were
    # already handled inside flush_doc_block since they sit at doc_block[0].
    {
        flush_doc_block()
    }

    END {
        # In case the file ends mid-block.
        flush_doc_block()
    }
' "$FILE")"

if [[ -z "$violations" ]]; then
    count=$(grep -c '@since [0-9]' "$FILE" || true)
    echo "lua_api_lint: ok ($count ---@since annotations)"
    exit 0
fi

echo "lua_api_lint: missing ---@since annotations in $FILE:" >&2
while IFS= read -r line; do
    case "$line" in
        MISSING:*)
            stripped="${line#MISSING:}"
            kind="${stripped%%:*}"
            rest="${stripped#*:}"
            num="${rest%%:*}"
            decl="${rest#*:}"
            printf "  %s:%s    [%s]  %s\n" "$FILE" "$num" "$kind" "$decl" >&2
            ;;
    esac
done <<< "$violations"

echo >&2
echo "Per docs/LUA_API_STABILITY.md, every public Lua surface must carry" >&2
echo "an ---@since X.Y.Z annotation in its preceding doc block." >&2
exit 1

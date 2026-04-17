-- poor-cli/config.lua
-- Configuration module for poor-cli Neovim plugin

local M = {}

-- Default configuration
M.defaults = {
    -- Server command to spawn
    server_cmd = "poor-cli-server --stdio",
    server_log_file = nil,
    
    -- Auto-start server on setup
    auto_start = true,
    auto_restart = true, -- Restart server automatically after unexpected exits
    restart_backoff_initial = 1000, -- Initial restart delay in ms
    restart_backoff_max = 30000, -- Max restart delay in ms
    restart_backoff_multiplier = 2, -- Backoff multiplier per failure
    
    -- Highlight group for ghost text
    ghost_text_hl = "Comment",
    
    -- Keymaps
    accept_key = "<Tab>",
    dismiss_key = "<Esc>",
    trigger_key = "<C-Space>",
    chat_key = "<leader>pc",
    checkpoints_key = nil,
    palette_key = "<leader>pp",
    
    -- Provider configuration (nil = auto-detect from environment)
    provider = nil,
    model = nil,
    api_key_env = nil,
    completion_provider = nil,
    completion_model = nil,
    rtk_enabled = true,

    -- UI options
    chat_width = 60,
    chat_position = "right",  -- "right" or "left"
    notifications = {
        group = "poor-cli",
        snacks = true,
    },
    max_context_files = 20, -- Maximum open buffers sent as chat context

    -- Mention picker behavior on `@` in chat:
    -- - "file"   (default) → jump straight to file picker; Claude-Code style.
    --                        Other sources reachable via manual `@buffer:` / `@lsp:`.
    -- - "buffer" / "lsp"   → same shortcut but defaults to that source.
    -- - "picker"           → show source picker (legacy multi-source flow).
    mentions = {
        default_source = "file",
    },
    diff_review = {
        mode = "review",
        layout = "unified",
        panel_position = "right",
        panel_width = 90,
        auto_open = true,
        risky_paths = { "package.json", "pyproject.toml", "Cargo.toml", "/main\\.", "/__init__\\." },
        risky_line_threshold = 50,
    },
    gitsigns = {
        ai_hunks = {
            enabled = true,
            glyph = "✱",
            hl = "PoorCLIAiHunk",
            priority = 5,
            toggle_key = "<leader>pg",
        },
    },
    neogit = {
        open_on_commit = false,
    },
    branches = {
        panel_width = 60,
        max_siblings = 20,
    },
    prompt_dir = nil,
    cost = {
        enabled = true,
        show_turn_badges = true,
        alarm_session = 5.0,
        alarm_daily = 20.0,
    },
    chat_export = {
        dir = nil,
        default_format = "markdown",
    },
    provider_picker = {
        cost_overrides = {},
    },
    
    -- Auto-completion settings
    auto_trigger = false,  -- Auto-trigger on TextChangedI (debounced)
    trigger_delay = 500,   -- Debounce delay in ms for auto-trigger
    request_timeout = 15000, -- RPC request timeout in ms
    auto_fix_diagnostics = false, -- Auto-suggest fix for error diagnostics
    diagnostics_enabled = false, -- Show assistant file:line suggestions as diagnostics
    dap = {
        keymaps_enabled = true,
        breakpoint_key = "<leader>pb",
        run_key = "<leader>pB",
    },
    completion_enabled = true,
    completion_manual_only = false,
    completion_min_prefix = 0,
    completion_stream_partial = true,
    completion_max_lines_before = 80,
    completion_max_lines_after = 80,
    completion_max_chars = 16000,
    completion_lsp_context_max_chars = 4000,
    completion_candidates = 3,
    completion_filetype_allowlist = {},
    completion_filetype_blocklist = {},
    completion_buftype_blocklist = { "nofile", "prompt", "quickfix", "terminal" },

    -- Keymap for partial word acceptance
    accept_word_key = "<C-Right>", -- accept next word of ghost text
    accept_line_key = "<M-l>", -- accept next line of ghost text
    cycle_next_key = "<M-]>",
    cycle_prev_key = "<M-[>",

    -- Health check on setup
    check_health_on_setup = false,

    -- Test file naming patterns per language group
    -- Keys: language group name, Values: pattern string with {base} and {ext} placeholders
    test_file_patterns = {
        default = "test_{base}.{ext}",
        javascript = "{base}.test.{ext}",
        typescript = "{base}.test.{ext}",
        typescriptreact = "{base}.test.{ext}",
        rust = "{base}_test.{ext}",
    },

    -- Debug mode
    debug = false,

    -- Verbose RPC echo: show per-request "⏳ method" feedback in :messages.
    -- Disabled by default to reduce terminal noise; enable for debugging.
    verbose_rpc = false,

    -- Per-tool permission allow/deny-list. Complements permission_mode:
    --   allow = {...} — these tools auto-approve without showing the modal.
    --   deny  = {...} — these tools auto-reject without showing the modal.
    -- Entry format:
    --   "tool_name"            — matches any invocation of that tool
    --   "tool_name:pattern"    — pattern is a glob (`*` → any). Matches
    --                             against vim.inspect(args), so e.g.
    --                             "bash:*pip install*" auto-allows pip
    --                             installs, "bash:*rm -rf*" auto-denies
    --                             dangerous deletes.
    -- deny is checked first; a tool in both lists gets denied.
    permission = {
        allow = {},
        deny = {},
    },

    -- Session trace. When true, every interesting event flows into a
    -- unified log line format in :messages:
    --   [poor-cli log HH:MM:SS.mmm] <category> <detail>
    -- Categories:
    --   input  — :PoorCLI* command invocations + chat sends
    --   rpc    — outgoing RPC method names (forwarded from verbose_rpc)
    --   state  — server state transitions + api-key validity flips
    --   event  — tool calls, permission decisions, turn boundaries,
    --             server crashes
    -- ON by default so bug reports naturally include the trace; turn off
    -- via :PoorCLIInputLog off if the :messages noise gets in your way.
    log_user_input = true,

    -- Chat turn tracing:
    --   "off"     — no trace toasts (default)
    --   "basic"   — toast when message sent, when provider returns first
    --               token, and when the turn finishes (tokens + cost + elapsed)
    --   "verbose" — basic + "💭 thinking started/ended" brackets around
    --               any chain-of-thought the provider emits.
    --               Requires a model that reports the EXTENDED_THINKING
    --               capability (Anthropic Claude with extended thinking,
    --               OpenAI reasoning-mode models). If the active provider
    --               doesn't support it, the plugin surfaces a one-time
    --               notice and the basic traces still fire.
    -- Toggle at runtime with :PoorCLIChatTrace [off|basic|verbose].
    chat_trace = "off",

    -- opt-in UX features (off by default; set true to enable)
    ux = {
        command_palette = false,        -- :PoorCLIHelp palette fuzzy-find across all commands
        streaming_indicator = false,    -- virt_text "[streaming... q cancel]" in chat buffer
        auto_onboarding = false,        -- auto-surface onboarding when API key missing
        inline_cycle_hint = false,      -- ghost-text "1/3" candidate counter
        cost_lualine_auto = false,      -- auto-register cost component in lualine
        diff_accept_all = false,        -- gAA accept-all shortcut in diff review
        context_remove_files = false,   -- 'd' in context panel marks file excluded from next send
        home_nav = false,               -- :PoorCLIHelp keymaps / home-nav: close aux windows, return to editor
        provider_cost_preview = false,  -- cost column in provider picker
        inline_status_lualine = false,  -- realtime inline completion status in lualine
        chat_history_search = false,    -- '?' in chat buffer filters turns
        completion_reason = false,      -- :PoorCLIDiag status shows completion-disabled reason
        health_actions = false,         -- :checkhealth entries include actionable cmd hints
    },
}

-- Current configuration (merged with user options)
M.config = vim.deepcopy(M.defaults)

-- Setup function to merge user options
function M.setup(opts)
    opts = opts or {}
    -- load keybinding prefs from onboarding wizard (if any)
    local prefs_path = vim.fs.joinpath(M.get_state_dir(), "keybinding_prefs.json")
    local prefs_file = io.open(prefs_path, "r")
    if prefs_file then
        local decode = vim.json and vim.json.decode or vim.fn.json_decode
        local ok, prefs = pcall(decode, prefs_file:read("*a"))
        prefs_file:close()
        if ok and type(prefs) == "table" then
            for k, v in pairs(prefs) do
                if M.defaults[k] ~= nil then M.defaults[k] = v end
            end
        end
    end
    M.config = vim.tbl_deep_extend("force", M.defaults, opts)

    -- validate known enum-like config values
    local valid_chat_pos = { right = true, left = true }
    if M.config.chat_position and not valid_chat_pos[M.config.chat_position] then
        require("poor-cli.notify").notify("[poor-cli] invalid chat_position '" .. tostring(M.config.chat_position) .. "', using 'right'", vim.log.levels.WARN)
        M.config.chat_position = "right"
    end
    -- warn on unrecognized top-level keys
    for k, _ in pairs(opts) do
        if M.defaults[k] == nil then
            require("poor-cli.notify").notify("[poor-cli] unknown config key: " .. tostring(k), vim.log.levels.WARN)
        end
    end

    if M.config.debug then
        require("poor-cli.notify").notify("[poor-cli] Config loaded: " .. vim.inspect(M.config), vim.log.levels.DEBUG)
    end
    
    return M.config
end

-- Get a config value
function M.get(key)
    return M.config[key]
end

-- Check if debug mode is enabled
function M.is_debug()
    return M.config.debug
end

function M.get_state_dir()
    local dir = vim.fs.joinpath(vim.fn.stdpath("state"), "poor-cli")
    vim.fn.mkdir(dir, "p")
    return dir
end

function M.get_server_log_file()
    local configured = M.get("server_log_file")
    if configured and configured ~= "" then
        local absolute = vim.fn.fnamemodify(configured, ":p")
        local parent = vim.fn.fnamemodify(absolute, ":h")
        vim.fn.mkdir(parent, "p")
        return absolute
    end

    return vim.fs.joinpath(M.get_state_dir(), "server.log")
end

function M.sanitized_for_debug()
    local debug_config = vim.deepcopy(M.config)
    debug_config.api_key_env = nil
    return debug_config
end

return M

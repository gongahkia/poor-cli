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

    -- Multiplayer remote bridge mode
    multiplayer = {
        enabled = false,
        invite = nil,
    },
    
    -- UI options
    chat_width = 60,
    chat_position = "right",  -- "right" or "left"
    max_context_files = 20, -- Maximum open buffers sent as chat context
    
    -- Auto-completion settings
    auto_trigger = false,  -- Auto-trigger on TextChangedI (debounced)
    trigger_delay = 500,   -- Debounce delay in ms for auto-trigger
    request_timeout = 15000, -- RPC request timeout in ms
    auto_fix_diagnostics = false, -- Auto-suggest fix for error diagnostics
    diagnostics_enabled = false, -- Show assistant file:line suggestions as diagnostics
    completion_enabled = true,
    completion_manual_only = false,
    completion_min_prefix = 0,
    completion_stream_partial = true,
    completion_max_lines_before = 80,
    completion_max_lines_after = 80,
    completion_max_chars = 16000,
    completion_lsp_context_max_chars = 4000,
    completion_filetype_allowlist = {},
    completion_filetype_blocklist = {},
    completion_buftype_blocklist = { "nofile", "prompt", "quickfix", "terminal" },

    -- Keymap for partial word acceptance
    accept_word_key = "<C-Right>", -- accept next word of ghost text

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
        vim.notify("[poor-cli] invalid chat_position '" .. tostring(M.config.chat_position) .. "', using 'right'", vim.log.levels.WARN)
        M.config.chat_position = "right"
    end
    -- warn on unrecognized top-level keys
    for k, _ in pairs(opts) do
        if M.defaults[k] == nil then
            vim.notify("[poor-cli] unknown config key: " .. tostring(k), vim.log.levels.WARN)
        end
    end

    if M.config.debug then
        vim.notify("[poor-cli] Config loaded: " .. vim.inspect(M.config), vim.log.levels.DEBUG)
    end
    
    return M.config
end

-- Get a config value
function M.get(key)
    return M.config[key]
end

function M.set_multiplayer_bootstrap(opts)
    local multiplayer = vim.deepcopy(M.config.multiplayer or {})
    multiplayer.enabled = opts and opts.enabled == true or false
    multiplayer.invite = opts and opts.invite or nil
    M.config.multiplayer = multiplayer
    return multiplayer
end

function M.clear_multiplayer_bootstrap()
    return M.set_multiplayer_bootstrap({
        enabled = false,
        invite = nil,
    })
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
    local multiplayer = debug_config.multiplayer
    if type(multiplayer) == "table" then
        if multiplayer.invite then
            multiplayer.invite = "<redacted>"
        end
    end
    return debug_config
end

return M

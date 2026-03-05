-- poor-cli/config.lua
-- Configuration module for poor-cli Neovim plugin

local M = {}

-- Default configuration
M.defaults = {
    -- Server command to spawn
    server_cmd = "poor-cli-server --stdio",
    
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
    
    -- Provider configuration (nil = auto-detect from environment)
    provider = nil,
    model = nil,
    api_key_env = nil,

    -- Multiplayer remote bridge mode
    multiplayer = {
        enabled = false,
        url = nil,
        room = nil,
        token = nil,
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

    -- Keymaps for partial acceptance
    accept_line_key = "<Tab>",   -- Accept current line of ghost text
    accept_word_key = "<C-Right>", -- Accept next word of ghost text

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
    M.config = vim.tbl_deep_extend("force", M.defaults, opts)
    
    if M.config.debug then
        vim.notify("[poor-cli] Config loaded: " .. vim.inspect(M.config), vim.log.levels.DEBUG)
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

return M

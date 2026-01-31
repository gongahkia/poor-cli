-- poor-cli/config.lua
-- Configuration module for poor-cli Neovim plugin

local M = {}

-- Default configuration
M.defaults = {
    -- Server command to spawn
    server_cmd = "poor-cli-server --stdio",
    
    -- Auto-start server on setup
    auto_start = true,
    
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
    
    -- UI options
    chat_width = 60,
    chat_position = "right",  -- "right" or "left"
    
    -- Auto-completion settings
    auto_trigger = false,  -- Auto-trigger on CursorHoldI
    trigger_delay = 500,   -- Delay in ms for auto-trigger
    
    -- Health check on setup
    check_health_on_setup = false,
    
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

-- minimal_init.lua
-- Minimal Neovim configuration for testing poor-cli plugin in isolation

-- Set up runtime path to include the plugin
local plugin_root = vim.fn.fnamemodify(vim.fn.expand("<sfile>:h"), ":h")
vim.opt.runtimepath:prepend(plugin_root)

-- Also add plenary.nvim for testing (expected to be in same parent directory or installed)
local plenary_path = vim.fn.expand("~/.local/share/nvim/site/pack/vendor/start/plenary.nvim")
if vim.fn.isdirectory(plenary_path) == 1 then
    vim.opt.runtimepath:prepend(plenary_path)
end

-- Disable some features for cleaner testing
vim.opt.swapfile = false
vim.opt.backup = false
vim.opt.writebackup = false

-- Set up minimal options
vim.opt.termguicolors = true
vim.opt.hidden = true
vim.opt.updatetime = 300

-- Mock server command for testing (uses echo to avoid needing real server)
local test_config = {
    server_cmd = "echo 'test-server'",  -- Will be overridden in tests
    auto_start = false,  -- Don't auto-start in tests
    debug = true,        -- Enable debug logging for tests
    ghost_text_hl = "Comment",
    trigger_key = "<C-Space>",
    accept_key = "<Tab>",
    dismiss_key = "<Esc>",
    chat_key = "<leader>pc",
}

-- Load and setup the plugin with test config
local ok, poor_cli = pcall(require, "poor-cli")
if ok then
    poor_cli.setup(test_config)
    print("[test] poor-cli loaded successfully")
else
    print("[test] Failed to load poor-cli: " .. tostring(poor_cli))
end

-- Helper function for tests
_G.test_helpers = {
    -- Create a temporary buffer with content
    create_buffer = function(lines, filetype)
        local buf = vim.api.nvim_create_buf(true, false)
        vim.api.nvim_buf_set_lines(buf, 0, -1, false, lines)
        if filetype then
            vim.bo[buf].filetype = filetype
        end
        vim.api.nvim_set_current_buf(buf)
        return buf
    end,
    
    -- Get buffer content as string
    get_buffer_content = function(buf)
        buf = buf or vim.api.nvim_get_current_buf()
        local lines = vim.api.nvim_buf_get_lines(buf, 0, -1, false)
        return table.concat(lines, "\n")
    end,
    
    -- Wait for condition with timeout
    wait_for = function(condition, timeout_ms, check_interval_ms)
        timeout_ms = timeout_ms or 1000
        check_interval_ms = check_interval_ms or 50
        local start = vim.loop.now()
        while vim.loop.now() - start < timeout_ms do
            if condition() then
                return true
            end
            vim.wait(check_interval_ms)
        end
        return false
    end,
    
    -- Clean up after test
    cleanup = function()
        -- Close all buffers except the first
        for _, buf in ipairs(vim.api.nvim_list_bufs()) do
            if vim.api.nvim_buf_is_valid(buf) and buf ~= 1 then
                vim.api.nvim_buf_delete(buf, { force = true })
            end
        end
        
        -- Clear ghost text
        local inline = require("poor-cli.inline")
        if inline then
            inline.clear_ghost_text()
        end
    end,
}

print("[test] minimal_init.lua loaded")

-- poor-cli/health.lua
-- Health check for poor-cli plugin

local M = {}

function M.check()
    local health = vim.health or require("health")
    local start = health.start or health.report_start
    local ok = health.ok or health.report_ok
    local warn = health.warn or health.report_warn
    local error = health.error or health.report_error
    local info = health.info or health.report_info
    
    start("poor-cli")
    
    -- Check Neovim version
    if vim.fn.has("nvim-0.9") == 1 then
        ok("Neovim version: " .. vim.version().major .. "." .. vim.version().minor)
    else
        warn("Neovim 0.9+ recommended for best experience")
    end
    
    -- Check for poor-cli-server binary
    local server_path = vim.fn.exepath("poor-cli-server")
    if server_path ~= "" then
        ok("poor-cli-server found: " .. server_path)
    else
        error("poor-cli-server not found in PATH")
        info("Install with: pip install poor-cli")
    end
    
    -- Check Python version
    local python_version = vim.fn.system("python3 --version 2>&1")
    if vim.v.shell_error == 0 then
        local version = python_version:match("Python (%d+%.%d+)")
        if version then
            local major, minor = version:match("(%d+)%.(%d+)")
            if tonumber(major) >= 3 and tonumber(minor) >= 8 then
                ok("Python version: " .. version)
            else
                warn("Python 3.8+ recommended, found: " .. version)
            end
        end
    else
        warn("Python not found or error checking version")
    end
    
    -- Check for required Python packages
    local packages = { "google-generativeai", "aiohttp", "rich" }
    for _, pkg in ipairs(packages) do
        local result = vim.fn.system("python3 -c \"import " .. pkg:gsub("-", "_") .. "\" 2>&1")
        if vim.v.shell_error == 0 then
            ok("Python package: " .. pkg)
        else
            warn("Python package not found: " .. pkg)
        end
    end
    
    -- Check for API keys
    local env_vars = {
        { name = "GEMINI_API_KEY", provider = "Gemini" },
        { name = "OPENAI_API_KEY", provider = "OpenAI" },
        { name = "ANTHROPIC_API_KEY", provider = "Claude/Anthropic" },
    }
    
    local has_any_key = false
    for _, env in ipairs(env_vars) do
        if vim.env[env.name] and vim.env[env.name] ~= "" then
            ok("API key configured: " .. env.provider)
            has_any_key = true
        end
    end
    
    if not has_any_key then
        warn("No API keys found. Set GEMINI_API_KEY, OPENAI_API_KEY, or ANTHROPIC_API_KEY")
    end
    
    -- Check server status
    local rpc = require("poor-cli.rpc")
    if rpc.is_running() then
        ok("Server is running")
    else
        info("Server is not running. Use :PoorCliStart to start")
    end
    
    -- Check treesitter (optional but recommended)
    local has_treesitter = pcall(require, "nvim-treesitter")
    if has_treesitter then
        ok("nvim-treesitter available")
    else
        info("nvim-treesitter not found. Some features like :PoorCliDoc may be limited")
    end
end

return M

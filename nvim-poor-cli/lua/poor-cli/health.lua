-- poor-cli/health.lua
-- Health check for poor-cli plugin

local M = {}

local function command_display(cmd)
    if type(cmd) == "table" then
        return table.concat(cmd, " ")
    end
    return tostring(cmd or "")
end

function M.check()
    local health = vim.health or require("health")
    local start = health.start or health.report_start
    local ok = health.ok or health.report_ok
    local warn = health.warn or health.report_warn
    local error = health.error or health.report_error
    local info = health.info or health.report_info
    local config = require("poor-cli.config")
    local rpc = require("poor-cli.rpc")

    start("poor-cli")

    if vim.fn.has("nvim-0.9") == 1 then
        ok("Neovim version: " .. vim.version().major .. "." .. vim.version().minor)
    else
        warn("Neovim 0.9+ recommended for best experience")
    end

    local server_cmd, resolve_err = rpc.resolve_server_command()
    if resolve_err then
        error(resolve_err)
    else
        info("Configured server command: " .. command_display(server_cmd))
        if type(server_cmd) == "table" then
            local executable = vim.fn.exepath(server_cmd[1])
            if executable ~= "" then
                ok("Resolved server executable: " .. executable)
            else
                error("Server executable not found: " .. tostring(server_cmd[1]))
            end
        else
            info("Shell command configured; health cannot fully validate executable resolution")
        end
    end

    local log_path = config.get_server_log_file()
    local log_dir = vim.fn.fnamemodify(log_path, ":h")
    if vim.fn.isdirectory(log_dir) == 1 then
        ok("Server log directory exists: " .. log_dir)
    else
        warn("Server log directory missing: " .. log_dir)
    end
    info("Server log file: " .. log_path)

    local python_version = vim.fn.system("python3 --version 2>&1")
    if vim.v.shell_error == 0 then
        local version = python_version:match("Python (%d+%.%d+)")
        if version then
            local major, minor = version:match("(%d+)%.(%d+)")
            if tonumber(major) > 3 or (tonumber(major) == 3 and tonumber(minor) >= 9) then
                ok("Python version: " .. version)
            else
                warn("Python 3.9+ required, found: " .. version)
            end
        end
    else
        warn("Python not found or error checking version")
    end

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

    local status = rpc.get_status()
    if rpc.is_running() then
        ok("Server is running (" .. tostring(status.state) .. ")")
        local provider_info = status.provider_info or {}
        if type(provider_info) == "table" and provider_info.name then
            ok("Initialized provider: " .. tostring(provider_info.name) .. "/" .. tostring(provider_info.model))
        else
            warn("Server is running but provider info is unavailable")
        end
    else
        info("Server is not running. Use :PoorCliStart to start")
    end

    if status.last_error_message and status.last_error_message ~= "" then
        warn("Last server error: " .. status.last_error_message)
    end

    if status.last_stderr_excerpt and status.last_stderr_excerpt ~= "" then
        info("Recent server stderr:\n" .. status.last_stderr_excerpt)
    end

    local has_treesitter = pcall(require, "nvim-treesitter")
    if has_treesitter then
        ok("nvim-treesitter available")
    else
        info("nvim-treesitter not found. Some features like :PoorCliDoc may be limited")
    end

    local has_cmp, cmp = pcall(require, "cmp")
    if has_cmp then
        ok("nvim-cmp available")
        local source_names = {}
        for _, source in ipairs(cmp.get_config().sources or {}) do
            table.insert(source_names, source.name)
        end
        if vim.tbl_contains(source_names, "poor-cli") then
            ok("poor-cli nvim-cmp source registered")
        else
            warn("nvim-cmp is installed but the poor-cli source is not active")
        end
    else
        info("nvim-cmp not found. poor-cli inline completion still works without cmp")
    end

    local has_blink = pcall(require, "blink.cmp")
    if has_blink then
        ok("blink.cmp available")
        info("Configure provider via require('poor-cli.blink').provider() in blink.cmp sources")
    else
        info("blink.cmp not found. poor-cli provides a source at require('poor-cli.blink')")
    end
end

return M

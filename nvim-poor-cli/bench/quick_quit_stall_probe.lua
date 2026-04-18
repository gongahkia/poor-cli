local function setup_runtime()
    local script_path = vim.fn.fnamemodify(debug.getinfo(1, "S").source:sub(2), ":p")
    local plugin_root = vim.fn.fnamemodify(script_path, ":h:h")
    vim.opt.runtimepath:prepend(plugin_root)
    package.path = table.concat({
        plugin_root .. "/lua/?.lua",
        plugin_root .. "/lua/?/init.lua",
        package.path,
    }, ";")

    package.preload["snacks"] = package.preload["snacks"] or function()
        local function noop() end
        return {
            notify = noop,
            notifier = { notify = noop },
        }
    end
    package.preload["trouble"] = package.preload["trouble"] or function()
        return {}
    end
    package.preload["dap"] = package.preload["dap"] or function()
        return {
            continue = function() end,
            toggle_breakpoint = function() end,
        }
    end
    package.preload["neogit"] = package.preload["neogit"] or function()
        return {}
    end
end

setup_runtime()
local script_path = vim.fn.fnamemodify(debug.getinfo(1, "S").source:sub(2), ":p")
local bench_dir = vim.fn.fnamemodify(script_path, ":h")
local stall_server = vim.fs.joinpath(bench_dir, "stall_server.py")
local wait_ms = tonumber(vim.env.POORCLI_BENCH_QUIT_WAIT_MS or "320") or 320
local exit_timeout_ms = tonumber(vim.env.POORCLI_BENCH_EXIT_TIMEOUT_MS or "180") or 180
local ultra_fast_raw = tostring(vim.env.POORCLI_BENCH_EXIT_ULTRA_FAST or "0"):lower()
local exit_ultra_fast = ultra_fast_raw == "1" or ultra_fast_raw == "true" or ultra_fast_raw == "yes"
require("poor-cli").setup({
    auto_start = true,
    check_health_on_setup = false,
    log_user_input = false,
    exit_stop_timeout_ms = exit_timeout_ms,
    exit_ultra_fast = exit_ultra_fast,
    server_cmd = { "python3", stall_server },
    notifications = { group = "poor-cli", snacks = false },
    startup_feedback_defer_ms = 999999,
    startup_success_notify = false,
    startup_probe_on_ready = false,
})

if wait_ms > 0 then
    vim.wait(wait_ms, function() return false end, 10)
end

vim.cmd("qa!")

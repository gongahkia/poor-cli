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
local auto_start = tostring(vim.env.POORCLI_BENCH_AUTO_START or "1"):lower()
auto_start = auto_start == "1" or auto_start == "true" or auto_start == "yes"
require("poor-cli").setup({
    auto_start = auto_start,
    check_health_on_setup = false,
    log_user_input = false,
    server_cmd = vim.env.POORCLI_BENCH_SERVER_CMD or "python3 -m poor_cli server --stdio",
    notifications = { group = "poor-cli", snacks = false },
})

local wait_ms = tonumber(vim.env.POORCLI_BENCH_QUIT_WAIT_MS or "0") or 0
if wait_ms > 0 then
    vim.wait(wait_ms, function() return false end, 10)
end

vim.cmd("qa!")

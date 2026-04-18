local uv = vim.uv or vim.loop

local function now_ns()
    if uv and uv.hrtime then
        return uv.hrtime()
    end
    return 0
end

local function ns_to_ms(ns)
    return (ns or 0) / 1000000
end

local function env_flag(name, default)
    local value = vim.env[name]
    if value == nil or value == "" then
        return default
    end
    value = tostring(value):lower()
    return value == "1" or value == "true" or value == "yes"
end

local function env_number(name, default)
    local value = tonumber(vim.env[name] or "")
    if value == nil then
        return default
    end
    return value
end

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

local function wait_until(timeout_ms, predicate)
    local ok = vim.wait(timeout_ms, predicate, 20)
    return ok == true
end

local function run_probe()
    setup_runtime()

    local auto_start = env_flag("POORCLI_BENCH_AUTO_START", false)
    local setup_timing = env_flag("POORCLI_BENCH_SETUP_TIMING", false)
    local wait_setup_ms = env_number("POORCLI_BENCH_SETUP_WAIT_MS", 5000)
    local wait_ready_ms = env_number("POORCLI_BENCH_READY_WAIT_MS", 20000)
    local server_cmd = vim.env.POORCLI_BENCH_SERVER_CMD or "python3 -m poor_cli server --stdio"
    if setup_timing then
        vim.env.POORCLI_SETUP_TIMING = "1"
    end

    local t0 = now_ns()
    local poor_cli = require("poor-cli")
    local t_require = now_ns()

    poor_cli.setup({
        auto_start = auto_start,
        check_health_on_setup = false,
        log_user_input = false,
        server_cmd = server_cmd,
        notifications = { group = "poor-cli", snacks = false },
    })
    local t_setup_return = now_ns()
    local first_tick_done = false
    local t_first_tick = 0
    vim.schedule(function()
        t_first_tick = now_ns()
        first_tick_done = true
    end)
    local first_tick_ready = wait_until(wait_setup_ms, function()
        return first_tick_done
    end)

    local setup_done = wait_until(wait_setup_ms, function()
        return poor_cli._setup_complete == true
    end)
    local t_setup_done = now_ns()

    local ready_done = false
    local t_ready = 0
    if auto_start then
        ready_done = wait_until(wait_ready_ms, function()
            local rpc = require("poor-cli.rpc")
            return rpc.get_status().state == "ready"
        end)
        t_ready = now_ns()
    end

    local status = require("poor-cli.rpc").get_status()
    local payload = {
        auto_start = auto_start,
        setup_timing_enabled = setup_timing,
        setup_done = setup_done,
        ready_done = ready_done,
        server_state = status.state,
        require_ms = ns_to_ms(t_require - t0),
        setup_return_ms = ns_to_ms(t_setup_return - t0),
        setup_complete_ms = ns_to_ms(t_setup_done - t0),
        first_tick_ms = first_tick_ready and ns_to_ms(t_first_tick - t_setup_return) or nil,
        ready_ms = auto_start and ns_to_ms(t_ready - t0) or nil,
    }
    if setup_timing and type(poor_cli.get_setup_timing) == "function" then
        local rows = poor_cli.get_setup_timing() or {}
        local timing_map = {}
        for _, row in ipairs(rows) do
            if type(row) == "table" and row.name ~= nil and row.ms ~= nil then
                timing_map[tostring(row.name)] = tonumber(row.ms) or 0
            end
        end
        payload.setup_timing_ms = timing_map
    end

    io.stdout:write(vim.json.encode(payload) .. "\n")
    io.stdout:flush()

    local rpc = require("poor-cli.rpc")
    if rpc and type(rpc.stop_for_exit) == "function" then
        rpc.stop_for_exit()
    elseif rpc and type(rpc.stop) == "function" then
        rpc.stop()
    end
end

run_probe()
vim.cmd("qa!")

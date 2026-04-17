local rpc = require("poor-cli.rpc")
local pickers = require("poor-cli.pickers")

local M = {}

M.buf = nil
M.win = nil
M.state = {
    tab = "configured",
    servers = {},
    registry = { enabled = false, servers = {} },
    query = "",
    page = 0,
    limit = 20,
}
M.line_actions = {}
M.badges = {}
M.ns = vim.api.nvim_create_namespace("poor-cli_mcp_registry")

local function json_encode(value)
    return (vim.json and vim.json.encode or vim.fn.json_encode)(value)
end

local function json_decode(value)
    return (vim.json and vim.json.decode or vim.fn.json_decode)(value)
end

local function clip(value, width)
    local text = tostring(value or ""):gsub("\n.*", "")
    if #text <= width then return text end
    return text:sub(1, math.max(1, width - 3)) .. "..."
end

local function status_for(server)
    if server.enabled == false then return "disabled", "Comment" end
    local err = server.lastError or server.error
    if err and err ~= "" then return "error", "ErrorMsg" end
    if server.status == "healthy" or server.connected == true then return "healthy", "DiagnosticOk" end
    return tostring(server.status or "unknown"), "WarningMsg"
end

local function server_line(server)
    local status = status_for(server)
    local name = clip(server.name or "unknown", 28)
    local transport = clip(server.transport or "stdio", 8)
    local tools = tostring(server.toolCount or server.tools_count or 0) .. " tools"
    local err = server.lastError and server.lastError ~= "" and ("  error: " .. clip(server.lastError, 50)) or ""
    return string.format("  %-28s %-8s %-10s %s%s", name, transport, status, tools, err)
end

local function tab_header(active)
    local a = active == "configured" and "[CONFIGURED]" or " configured "
    local b = active == "browse" and "[BROWSE]" or " browse "
    return a .. "  " .. b
end

local function configured_footer()
    return {
        "t toggle  e edit  x remove  h health  c test-tool",
        "gt tabs  r refresh  q close",
    }
end

local function browse_footer()
    return {
        "s search  n next-page  p prev-page  i install",
        "gt tabs  r refresh  q close",
    }
end

local function render_configured(state)
    local lines = {
        "# poor-cli mcp",
        tab_header("configured"),
        "",
    }
    local servers = state.servers or {}
    local actions, badges = {}, {}
    if #servers == 0 then
        table.insert(lines, "  no MCP servers configured")
    end
    for _, server in ipairs(servers) do
        local status, hl = status_for(server)
        table.insert(lines, server_line(server))
        actions[#lines] = { kind = "server", server = server }
        local start_col = (lines[#lines]:find(status, 1, true) or 1) - 1
        badges[#lines] = { col = start_col, len = #status, hl = hl }
    end
    table.insert(lines, "")
    for _, line in ipairs(configured_footer()) do table.insert(lines, line) end
    return lines, actions, badges
end

local function render_browse(state)
    local lines = {
        "# poor-cli mcp",
        tab_header("browse"),
        "",
        "query: " .. tostring(state.query or "") .. "  page: " .. tostring((state.page or 0) + 1),
        "",
    }
    local registry = state.registry or {}
    local actions = {}
    local results = registry.servers or registry.items or registry.results or {}
    if registry.enabled == false then
        table.insert(lines, "  registry pull disabled")
    elseif #results == 0 then
        table.insert(lines, "  no registry results (press s to search)")
    else
        for _, item in ipairs(results) do
            local name = item.name or item.id or item.packageName or "unknown"
            table.insert(lines, "  " .. clip(name, 72))
            actions[#lines] = { kind = "registry", item = item }
            if item.description and item.description ~= "" then
                table.insert(lines, "    " .. clip(item.description, 90))
                actions[#lines] = { kind = "registry", item = item }
            end
        end
    end
    table.insert(lines, "")
    for _, line in ipairs(browse_footer()) do table.insert(lines, line) end
    return lines, actions, {}
end

function M.render_lines(state)
    state = state or M.state
    if state.tab == "browse" then
        return render_browse(state)
    end
    return render_configured(state)
end

local function apply_badges()
    if not (M.buf and vim.api.nvim_buf_is_valid(M.buf)) then return end
    vim.api.nvim_buf_clear_namespace(M.buf, M.ns, 0, -1)
    for line, badge in pairs(M.badges) do
        vim.api.nvim_buf_set_extmark(M.buf, M.ns, line - 1, badge.col, {
            end_col = badge.col + badge.len,
            hl_group = badge.hl,
        })
    end
end

function M.render()
    if not (M.buf and vim.api.nvim_buf_is_valid(M.buf)) then return end
    local lines
    lines, M.line_actions, M.badges = M.render_lines(M.state)
    vim.bo[M.buf].modifiable = true
    vim.api.nvim_buf_set_lines(M.buf, 0, -1, false, lines)
    vim.bo[M.buf].modifiable = false
    apply_badges()
end

local function set_state(result, err)
    vim.schedule(function()
        if err then require("poor-cli.notify").notify("[poor-cli] mcp: " .. rpc.format_error(err), vim.log.levels.ERROR); return end
        M.state.servers = (result or {}).servers or {}
        M.state.configPath = (result or {}).configPath
        M.state.registryAutodiscover = (result or {}).registryAutodiscover == true
        M.state.registry.enabled = M.state.registryAutodiscover
        M.render()
    end)
end

function M.refresh()
    rpc.mcp_list({}, set_state)
end

local function current_action()
    local line = vim.api.nvim_win_get_cursor(M.win or 0)[1]
    return M.line_actions[line]
end

local function confirm_write(message)
    return vim.fn.confirm(message .. "\nwrite .poor-cli/mcp.json?", "&Yes\n&No", 2) == 1
end

local function mutate(method, params)
    rpc[method](params, set_state)
end

function M.toggle()
    local action = current_action()
    if not (action and action.server) then return end
    local server = action.server
    if not confirm_write("toggle " .. tostring(server.name)) then return end
    mutate("mcp_toggle", { name = server.name, confirmed = true })
end

function M.remove()
    local action = current_action()
    if not (action and action.server) then return end
    local name = tostring(action.server.name or "")
    if not confirm_write("remove " .. name) then return end
    mutate("mcp_remove", { name = name, confirmed = true })
end

function M.edit()
    local action = current_action()
    if not (action and action.server) then return end
    local default = json_encode(action.server)
    vim.ui.input({ prompt = "server spec json: ", default = default }, function(raw)
        if not raw or raw == "" then return end
        local ok, spec = pcall(json_decode, raw)
        if not ok or type(spec) ~= "table" then require("poor-cli.notify").notify("[poor-cli] invalid json", vim.log.levels.ERROR); return end
        if not confirm_write("edit " .. tostring(spec.name or action.server.name)) then return end
        mutate("mcp_edit", { server = spec, confirmed = true })
    end)
end

function M.health()
    local action = current_action()
    local name = action and action.server and action.server.name or nil
    rpc.mcp_health({ name = name }, function(result, err)
        vim.schedule(function()
            if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
            require("poor-cli.notify").notify("[poor-cli] mcp health: " .. vim.inspect((result or {}).servers or {}), vim.log.levels.INFO)
            M.refresh()
        end)
    end)
end

function M.test_tool()
    local action = current_action()
    local prefix = action and action.server and action.server.name and (action.server.name .. ":") or ""
    vim.ui.input({ prompt = "tool: ", default = prefix }, function(tool)
        if not tool or tool == "" then return end
        vim.ui.input({ prompt = "arguments json: ", default = "{}" }, function(raw)
            local ok, args = pcall(json_decode, raw or "{}")
            if not ok or type(args) ~= "table" then require("poor-cli.notify").notify("[poor-cli] invalid json", vim.log.levels.ERROR); return end
            rpc.mcp_test({ tool = tool, arguments = args }, function(result, err)
                vim.schedule(function()
                    if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
                    local float_win = require("poor-cli.float_win")
                    local output = tostring((result or {}).result or "")
                    float_win.open_lines(vim.split(output, "\n", { plain = true }), {
                        filetype = "markdown",
                        name = "[poor-cli mcp test]",
                        title = " mcp test ",
                        width = 0.7, height = 0.6, position = "center",
                    })
                end)
            end)
        end)
    end)
end

local function registry_preview(item)
    return table.concat({
        tostring(item.name or item.id or "unknown"),
        "",
        tostring(item.description or ""),
        "",
        json_encode(item),
    }, "\n")
end

local function registry_spec(item)
    local name = item.name or item.id or item.packageName or item.package_name
    if not name and type(item.package) == "table" then name = item.package.name end
    local spec = { name = tostring(name or "mcp-server"), enabled = false }
    if item.transport then spec.transport = item.transport end
    if item.url then spec.transport = spec.transport or "http"; spec.url = item.url end
    if item.command then spec.transport = spec.transport or "stdio"; spec.command = item.command end
    if not spec.transport then spec.transport = spec.url and "http" or "stdio" end
    return spec
end

function M.install_registry_item(item)
    local spec = registry_spec(item)
    if not confirm_write("add disabled MCP server " .. tostring(spec.name)) then return end
    mutate("mcp_edit", { server = spec, confirmed = true })
end

function M.registry_fetch()
    local offset = (M.state.page or 0) * (M.state.limit or 20)
    rpc.mcp_registry_search({ query = M.state.query, limit = M.state.limit, offset = offset }, function(result, err)
        vim.schedule(function()
            if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
            M.state.registry = result or { enabled = false, servers = {} }
            M.render()
            if M.state.registry.enabled == false then require("poor-cli.notify").notify("[poor-cli] MCP registry disabled", vim.log.levels.WARN) end
        end)
    end)
end

function M.search_registry()
    vim.ui.input({ prompt = "registry query: ", default = M.state.query or "" }, function(query)
        if query == nil then return end
        M.state.query = query
        M.state.page = 0
        M.registry_fetch()
    end)
end

function M.next_page()
    M.state.page = (M.state.page or 0) + 1
    M.registry_fetch()
end

function M.prev_page()
    M.state.page = math.max(0, (M.state.page or 0) - 1)
    M.registry_fetch()
end

function M.install_current()
    local action = current_action()
    if action and action.item then M.install_registry_item(action.item) end
end

function M.cycle_tab(direction)
    direction = direction or 1
    local tabs = { "configured", "browse" }
    local idx = 1
    for i, t in ipairs(tabs) do if t == M.state.tab then idx = i; break end end
    idx = ((idx - 1 + direction) % #tabs) + 1
    M.state.tab = tabs[idx]
    if M.state.tab == "browse" and M.state.registry.enabled and (M.state.registry.servers == nil or #M.state.registry.servers == 0) then
        M.registry_fetch()
    else
        M.render()
    end
end

function M.close()
    if M.win and vim.api.nvim_win_is_valid(M.win) then vim.api.nvim_win_close(M.win, true) end
    M.win = nil
end

function M.open()
    if M.win and vim.api.nvim_win_is_valid(M.win) then
        vim.api.nvim_set_current_win(M.win)
        M.refresh()
        return M.buf
    end
    if not (M.buf and vim.api.nvim_buf_is_valid(M.buf)) then
        M.buf = vim.api.nvim_create_buf(false, true)
        vim.bo[M.buf].buftype = "nofile"
        vim.bo[M.buf].bufhidden = "hide"
        vim.bo[M.buf].swapfile = false
        vim.bo[M.buf].filetype = "poor-cli-mcp"
        vim.api.nvim_buf_set_name(M.buf, "[poor-cli mcp]")
    end
    local float_win = require("poor-cli.float_win")
    M.win = float_win.open(M.buf, {
        width = math.min(120, vim.o.columns - 4),
        height = math.max(24, vim.o.lines - 4),
        position = "center",
        title = " poor-cli mcp ",
        close_keys = {},
        wrap = false,
    })
    local map = function(lhs, fn, desc)
        vim.keymap.set("n", lhs, fn, { buffer = M.buf, nowait = true, desc = desc })
    end
    map("q", M.close, "Close MCP")
    map("<Esc>", M.close, "Close MCP")
    map("r", M.refresh, "Refresh MCP")
    map("gt", function() M.cycle_tab(1) end, "Next MCP tab")
    map("gT", function() M.cycle_tab(-1) end, "Prev MCP tab")
    map("t", M.toggle, "Toggle MCP server")
    map("e", M.edit, "Edit MCP server")
    map("x", M.remove, "Remove MCP server")
    map("h", M.health, "Health-check MCP server")
    map("c", M.test_tool, "Test MCP tool call")
    map("s", M.search_registry, "Search MCP registry")
    map("n", M.next_page, "Next registry page")
    map("p", M.prev_page, "Prev registry page")
    map("i", M.install_current, "Install registry MCP server")
    M.refresh()
    return M.buf
end

-- legacy picker entry for registry_pick (still used by some callers via M.registry_pick)
function M.registry_pick()
    rpc.mcp_registry_search({ query = M.state.query, limit = M.state.limit, offset = (M.state.page or 0) * (M.state.limit or 20) }, function(result, err)
        vim.schedule(function()
            if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
            M.state.registry = result or { enabled = false, servers = {} }
            if M.state.registry.enabled == false then require("poor-cli.notify").notify("[poor-cli] MCP registry disabled", vim.log.levels.WARN); return end
            local items = {}
            for _, item in ipairs(M.state.registry.servers or {}) do
                local name = item.name or item.id or item.packageName or "unknown"
                table.insert(items, { id = name, label = tostring(name), preview = registry_preview(item), data = { action = "install", item = item } })
            end
            pickers.pick(items, {
                title = "MCP registry",
                on_pick = function(data)
                    if data and data.action == "install" then M.install_registry_item(data.item) end
                end,
            })
        end)
    end)
end

return M

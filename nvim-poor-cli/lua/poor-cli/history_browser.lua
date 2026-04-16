local rpc = require("poor-cli.rpc")
local M = {}

function M.list(params, callback) return rpc.request("poor-cli/listHistory", params or {}, callback) end
function M.search(params, callback) return rpc.request("poor-cli/searchHistory", params or {}, callback) end
function M.export(params, callback) return rpc.request("poor-cli/exportConversation", params or {}, callback) end

local function notify(msg, level) require("poor-cli.notify").notify("[poor-cli] " .. msg, level) end

local function show_lines(title, content, filetype)
    local float_win = require("poor-cli.float_win")
    local lines = type(content) == "table"
        and content
        or vim.split(tostring(content), "\n", { plain = true })
    float_win.open_lines(lines, {
        filetype = filetype or "markdown",
        name = title,
        title = " " .. title:gsub("^%[", ""):gsub("%]$", "") .. " ",
        width = 0.8,
        height = 0.8,
        position = "center",
    })
end

local function format_entry(e)
    return string.format("[%s] %s  %s",
        tostring(e.timestamp or e.createdAt or "-"),
        tostring(e.role or "?"),
        tostring(e.summary or e.content or ""):sub(1, 80))
end

function M.open_picker(query)
    local pickers = require("poor-cli.pickers")
    if not rpc.is_running() then notify("server not running", vim.log.levels.WARN); return end
    local method = query and query ~= "" and "poor-cli/searchHistory" or "poor-cli/listHistory"
    local params = query and query ~= "" and { query = query } or {}
    rpc.request(method, params, function(result, err)
        vim.schedule(function()
            if err then notify(rpc.format_error(err), vim.log.levels.ERROR); return end
            local entries = (result or {}).entries or (result or {}).history or (result or {}).results or {}
            if #entries == 0 then notify("no history", vim.log.levels.INFO); return end
            local items = {}
            for _, e in ipairs(entries) do
                items[#items + 1] = {
                    label = format_entry(e),
                    preview = table.concat({
                        "Role: " .. tostring(e.role or "?"),
                        "Time: " .. tostring(e.timestamp or e.createdAt or "-"),
                        "",
                        tostring(e.content or e.summary or ""),
                    }, "\n"),
                    data = e,
                }
            end
            pickers.pick(items, { title = query and ("poor-cli history: " .. query) or "poor-cli history", on_pick = function(e)
                show_lines("[poor-cli history entry]", tostring(e.content or vim.inspect(e)), "markdown")
            end })
        end)
    end)
end

function M.setup()
    local function create_command(name, fn, opts) pcall(vim.api.nvim_del_user_command, name); vim.api.nvim_create_user_command(name, fn, opts or {}) end
    create_command("PoorCLIHistory", function() M.open_picker() end, { desc = "Browse history" })
    create_command("PoorCLIHistorySearch", function(opts) M.open_picker(opts.args) end, { nargs = 1, desc = "Search history" })
    create_command("PoorCLIHistoryPicker", function(opts)
        M.open_picker(opts.args ~= "" and opts.args or nil)
    end, { nargs = "?", desc = "Browse history (alias)" })
    create_command("PoorCLIExportConversation", function()
        M.export({}, function(result, err) vim.schedule(function()
            if err then notify(rpc.format_error(err), vim.log.levels.ERROR); return end
            local content = (result or {}).content or (result or {}).markdown or vim.inspect(result)
            show_lines("[poor-cli export]", content, "markdown")
        end) end)
    end, { desc = "Export conversation" })
end

return M

local rpc = require("poor-cli.rpc")
local M = {}

function M.list(params, callback) return rpc.request("poor-cli/memoryList", params or {}, callback) end
function M.save(params, callback) return rpc.request("poor-cli/memorySave", params or {}, callback) end
function M.search(params, callback) return rpc.request("poor-cli/memorySearch", params or {}, callback) end
function M.delete(params, callback) return rpc.request("poor-cli/memoryDelete", params or {}, callback) end

local function notify(msg, level) require("poor-cli.notify").notify("[poor-cli] " .. msg, level) end

local function show_lines(title, lines, filetype)
    local float_win = require("poor-cli.float_win")
    float_win.open_lines(lines, {
        filetype = filetype or "markdown",
        name = title,
        title = " " .. title:gsub("^%[", ""):gsub("%]$", "") .. " ",
        width = 0.7,
        height = 0.7,
        position = "center",
    })
end

local function format_memory(m)
    return string.format("%s: %s", tostring(m.key or "?"), tostring(m.value or m.summary or ""))
end

function M.open_picker(query)
    local pickers = require("poor-cli.pickers")
    if not rpc.is_running() then notify("server not running", vim.log.levels.WARN); return end
    local method = query and query ~= "" and "poor-cli/memorySearch" or "poor-cli/memoryList"
    local params = query and query ~= "" and { query = query } or {}
    rpc.request(method, params, function(result, err)
        vim.schedule(function()
            if err then notify(rpc.format_error(err), vim.log.levels.ERROR); return end
            local memories = (result or {}).memories or (result or {}).results or {}
            if #memories == 0 then notify("no memories found", vim.log.levels.INFO); return end
            local items = {}
            for _, m in ipairs(memories) do
                items[#items + 1] = {
                    id = tostring(m.key or ""),
                    label = format_memory(m),
                    preview = table.concat({
                        "Key: " .. tostring(m.key or "?"),
                        "Value: " .. tostring(m.value or ""),
                        "Created: " .. tostring(m.createdAt or "-"),
                        "Updated: " .. tostring(m.updatedAt or "-"),
                    }, "\n"),
                    data = m,
                }
            end
            pickers.pick(items, { title = query and ("poor-cli memory: " .. query) or "poor-cli memory", on_pick = function(m)
                vim.ui.select({ "delete", "copy" }, { prompt = "Action for " .. tostring(m.key) .. ":" }, function(choice)
                    if choice == "delete" then
                        M.delete({ key = m.key }, function(_, e) vim.schedule(function()
                            if e then notify(vim.inspect(e), vim.log.levels.ERROR)
                            else notify("memory deleted", vim.log.levels.INFO) end
                        end) end)
                    elseif choice == "copy" then
                        pcall(vim.fn.setreg, "+", tostring(m.value or ""))
                        notify("copied to clipboard", vim.log.levels.INFO)
                    end
                end)
            end })
        end)
    end)
end

function M.setup()
    local function create_command(name, fn, opts) pcall(vim.api.nvim_del_user_command, name); vim.api.nvim_create_user_command(name, fn, opts or {}) end
    create_command("PoorCLIMemory", function() M.open_picker() end, { desc = "Browse memory" })
    create_command("PoorCLIMemorySave", function()
        vim.ui.input({ prompt = "Memory key: " }, function(key)
            if not key or key == "" then return end
            vim.ui.input({ prompt = "Memory value: " }, function(value)
                if not value or value == "" then return end
                M.save({ key = key, value = value }, function(_, err) vim.schedule(function()
                    if err then notify(rpc.format_error(err), vim.log.levels.ERROR)
                    else notify("memory saved", vim.log.levels.INFO) end
                end) end)
            end)
        end)
    end, { desc = "Save memory" })
    create_command("PoorCLIMemorySearch", function(opts)
        M.open_picker(opts.args)
    end, { nargs = 1, desc = "Search memory" })
    create_command("PoorCLIMemoryDelete", function(opts)
        M.delete({ key = opts.args }, function(_, err) vim.schedule(function()
            if err then notify(rpc.format_error(err), vim.log.levels.ERROR)
            else notify("memory deleted", vim.log.levels.INFO) end
        end) end)
    end, { nargs = 1, desc = "Delete memory" })
    create_command("PoorCLIMemoryReview", function()
        if not rpc.is_running() then
            notify("server not running", vim.log.levels.WARN)
            return
        end
        rpc.request("poor-cli/memoryReviewList", {}, function(result, err)
            vim.schedule(function()
                if err then notify(rpc.format_error(err), vim.log.levels.ERROR); return end
                local pending = (result or {}).pending or {}
                local lines = { "# pending memories", "" }
                if #pending == 0 then
                    table.insert(lines, "no pending memories")
                else
                    for i, m in ipairs(pending) do
                        table.insert(lines, string.format("## %d. %s [%s]", i, m.name or "?", m.type or "?"))
                        table.insert(lines, m.description or "")
                        if m.content and m.content ~= "" then
                            for _, ln in ipairs(vim.split(m.content, "\n", { plain = true })) do
                                table.insert(lines, "  " .. ln)
                            end
                        end
                        table.insert(lines, "")
                        table.insert(lines, "  filename: " .. (m.filename or ""))
                        if m.sourceSessionId and m.sourceSessionId ~= "" then
                            table.insert(lines, "  source: " .. m.sourceSessionId .. " (" .. (m.extractor or "?") .. ")")
                        end
                        table.insert(lines, "")
                    end
                    table.insert(lines, "Actions: :PoorCLIMemoryReviewAccept <filename>  /  :PoorCLIMemoryReviewReject <filename>")
                    table.insert(lines, "Bulk:    :PoorCLIMemoryReviewBulk accept  /  reject")
                end
                show_lines("[poor-cli memory review]", lines, "markdown")
            end)
        end)
    end, { desc = "Review pending memory candidates" })
    create_command("PoorCLIMemoryReviewAccept", function(opts)
        local fname = opts.args
        if not fname or fname == "" then notify("filename required", vim.log.levels.WARN); return end
        rpc.request("poor-cli/memoryReviewAccept", { filename = fname }, function(result, err)
            vim.schedule(function()
                if err then notify(rpc.format_error(err), vim.log.levels.ERROR)
                else
                    local accepted = (result or {}).accepted
                    notify(accepted and "accepted" or "not found", vim.log.levels.INFO)
                end
            end)
        end)
    end, { nargs = 1, desc = "Accept a pending memory by filename" })
    create_command("PoorCLIMemoryReviewReject", function(opts)
        local fname = opts.args
        if not fname or fname == "" then notify("filename required", vim.log.levels.WARN); return end
        rpc.request("poor-cli/memoryReviewReject", { filename = fname }, function(_, err)
            vim.schedule(function()
                if err then notify(rpc.format_error(err), vim.log.levels.ERROR)
                else notify("rejected", vim.log.levels.INFO) end
            end)
        end)
    end, { nargs = 1, desc = "Reject a pending memory by filename" })
    create_command("PoorCLIMemoryReviewBulk", function(opts)
        local action = (opts.args or ""):lower()
        if action ~= "accept" and action ~= "reject" then
            notify("action must be 'accept' or 'reject'", vim.log.levels.WARN); return
        end
        rpc.request("poor-cli/memoryReviewBulk", { action = action }, function(result, err)
            vim.schedule(function()
                if err then notify(rpc.format_error(err), vim.log.levels.ERROR); return end
                local accepted = (result or {}).accepted or {}
                local rejected = (result or {}).rejected or {}
                notify(string.format("bulk %s: %d accepted, %d rejected", action, #accepted, #rejected), vim.log.levels.INFO)
            end)
        end)
    end, { nargs = 1, desc = "Bulk accept|reject pending memories" })
    create_command("PoorCLIMemoryExpiring", function()
        if not rpc.is_running() then
            notify("server not running", vim.log.levels.WARN); return
        end
        rpc.request("poor-cli/memoryExpiring", {}, function(result, err)
            vim.schedule(function()
                if err then notify(rpc.format_error(err), vim.log.levels.ERROR); return end
                local entries = (result or {}).expiring or {}
                local lines = { "# expiring memories", "" }
                if #entries == 0 then
                    table.insert(lines, "no memories due for expiry")
                    table.insert(lines, "")
                    table.insert(lines, "(MH3 forgetting policy: feedback never expires; user 365d; project 180d; reference 90d)")
                else
                    for _, m in ipairs(entries) do
                        table.insert(lines, string.format("- [%s] %s — last accessed %s, hits %d",
                            m.type or "?", m.name or "?",
                            m.lastAccessedAt or m.updatedAt or "?",
                            m.hitCount or 0))
                    end
                    table.insert(lines, "")
                    table.insert(lines, "Run :PoorCLIMemoryExpireRun to archive these (or :PoorCLIMemoryExpireRun dry).")
                end
                show_lines("[poor-cli memory expiring]", lines, "markdown")
            end)
        end)
    end, { desc = "List memories due for expiry" })
    create_command("PoorCLIMemoryExpireRun", function(opts)
        local dry = (opts.args or ""):lower() == "dry"
        rpc.request("poor-cli/memoryExpireRun", { dryRun = dry }, function(result, err)
            vim.schedule(function()
                if err then notify(rpc.format_error(err), vim.log.levels.ERROR); return end
                local archived = (result or {}).archived or {}
                local prefix = dry and "dry-run" or "archived"
                notify(string.format("%s %d memories", prefix, #archived), vim.log.levels.INFO)
            end)
        end)
    end, { nargs = "?", desc = "Archive expired memories (pass 'dry' for preview)" })
end

return M

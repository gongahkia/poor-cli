local rpc = require("poor-cli.rpc")
local M = {}

function M.create(params, callback) return rpc.request("poor-cli/createCheckpoint", params or {}, callback) end
function M.preview(params, callback) return rpc.request("poor-cli/previewCheckpoint", params or {}, callback) end
function M.restore(params, callback) return rpc.request("poor-cli/restoreCheckpoint", params or {}, callback) end
function M.gc(params, callback) return rpc.request("poor-cli/gcCheckpoints", params or {}, callback) end
function M.list(params, callback) return rpc.request("poor-cli/listCheckpoints", params or {}, callback) end

local function notify(msg, level) require("poor-cli.notify").notify("[poor-cli] " .. msg, level) end

local function show_lines(title, lines, filetype)
    local float_win = require("poor-cli.float_win")
    float_win.open_lines(lines, {
        filetype = filetype or "markdown",
        name = title,
        title = " " .. title:gsub("^%[", ""):gsub("%]$", "") .. " ",
        width = 0.6,
        height = 0.6,
        position = "center",
    })
end

local function preview_lines(id, r)
    r = r or {}
    local lines = {
        "# checkpoint preview: " .. tostring(id), "",
        "Files: " .. tostring(r.fileCount or 0),
        "Size: " .. tostring(r.totalSizeBytes or 0) .. " bytes",
        "Created: " .. tostring(r.createdAt or "-"),
        "Description: " .. tostring(r.description or ""),
        "",
    }
    local files = r.files or r.filePaths or {}
    if #files > 0 then
        table.insert(lines, "Affected files:")
        for _, f in ipairs(files) do table.insert(lines, "- " .. tostring(f)) end
    end
    return lines
end

function M.open_picker()
    local pickers = require("poor-cli.pickers")
    if not rpc.is_running() then notify("server not running", vim.log.levels.WARN); return end
    M.list({}, function(result, err)
        vim.schedule(function()
            if err then notify(rpc.format_error(err), vim.log.levels.ERROR); return end
            local data = result or {}
            if data.available == false then notify("checkpoint system unavailable", vim.log.levels.WARN); return end
            local cps = data.checkpoints or {}
            if #cps == 0 then notify("no checkpoints", vim.log.levels.INFO); return end
            local items = {}
            for _, cp in ipairs(cps) do
                local tags = (type(cp.tags) == "table" and #cp.tags > 0)
                    and (" [" .. table.concat(cp.tags, ",") .. "]") or ""
                items[#items + 1] = {
                    id = tostring(cp.checkpointId or "?"),
                    label = string.format("%s%s  %s  %.1f KB  %s",
                        cp.checkpointId or "?", tags,
                        tostring(cp.createdAt or ""),
                        (cp.totalSizeBytes or 0) / 1024,
                        tostring(cp.description or "")),
                    preview = table.concat({
                        "ID: " .. tostring(cp.checkpointId or "?"),
                        "Created: " .. tostring(cp.createdAt or "-"),
                        "Files: " .. tostring(cp.fileCount or 0),
                        "Size: " .. tostring(cp.totalSizeBytes or 0) .. " bytes",
                        "Tags: " .. (cp.tags and table.concat(cp.tags, ",") or ""),
                        "",
                        "Description: " .. tostring(cp.description or ""),
                    }, "\n"),
                    data = cp,
                }
            end
            pickers.pick(items, { title = "poor-cli checkpoints", on_pick = function(cp)
                local id = tostring(cp.checkpointId or "")
                vim.ui.select({ "preview", "restore" }, { prompt = "Action for " .. id .. ":" }, function(choice)
                    if not choice then return end
                    if choice == "preview" then
                        M.preview({ checkpointId = id }, function(r, e) vim.schedule(function()
                            if e then notify(rpc.format_error(e), vim.log.levels.ERROR); return end
                            show_lines("[poor-cli checkpoint preview]", preview_lines(id, r), "markdown")
                        end) end)
                    elseif choice == "restore" then
                        M.restore({ checkpointId = id }, function(_, e) vim.schedule(function()
                            if e then notify(rpc.format_error(e), vim.log.levels.ERROR)
                            else notify("restored " .. id, vim.log.levels.INFO) end
                        end) end)
                    end
                end)
            end })
        end)
    end)
end

function M.setup()
    require("poor-cli.command_spec").install("checkpoint", {
        desc = "Manage filesystem checkpoints",
        verb_names = { "list", "create", "preview", "gc" },
        verbs = {
            list = function() M.open_picker() end,
            create = function()
                vim.ui.input({ prompt = "Checkpoint label: " }, function(label)
                    if not label or label == "" then return end
                    M.create({ label = label }, function(result, err) vim.schedule(function()
                        if err then notify(rpc.format_error(err), vim.log.levels.ERROR)
                        else notify("checkpoint created: " .. tostring((result or {}).checkpointId or ""), vim.log.levels.INFO) end
                    end) end)
                end)
            end,
            preview = function(fargs)
                local id = fargs[1]
                if not id or id == "" then notify("usage: :PoorCLICheckpoint preview <id>", vim.log.levels.WARN); return end
                M.preview({ checkpointId = id }, function(result, err) vim.schedule(function()
                    if err then notify(rpc.format_error(err), vim.log.levels.ERROR); return end
                    show_lines("[poor-cli checkpoint preview]", preview_lines(id, result), "markdown")
                end) end)
            end,
            gc = function()
                M.gc({}, function(result, err) vim.schedule(function()
                    if err then notify(rpc.format_error(err), vim.log.levels.ERROR)
                    else notify("gc complete: " .. tostring((result or {}).removedCount or 0) .. " removed", vim.log.levels.INFO) end
                end) end)
            end,
        },
    })
end

return M

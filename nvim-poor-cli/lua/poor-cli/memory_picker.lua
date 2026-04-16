-- poor-cli/memory_picker.lua
-- MH8-UI: :PoorCLIMemoryPicker — list memories with hit_count / last_accessed,
-- sortable by hits desc | recency desc | name asc.

local M = {}

M.sort_modes = { "hits", "recency", "name" }
M._mode_idx = 1

local function sort_entries(entries, mode)
    local copy = {}
    for _, e in ipairs(entries) do copy[#copy + 1] = e end
    if mode == "hits" then
        table.sort(copy, function(a, b)
            return (tonumber(a.hitCount) or 0) > (tonumber(b.hitCount) or 0)
        end)
    elseif mode == "recency" then
        table.sort(copy, function(a, b)
            return tostring(a.lastAccessedAt or "") > tostring(b.lastAccessedAt or "")
        end)
    else -- name
        table.sort(copy, function(a, b)
            return tostring(a.name or "") < tostring(b.name or "")
        end)
    end
    return copy
end

local function format_label(entry, width)
    local name = tostring(entry.name or "?")
    local mtype = tostring(entry.type or "?"):sub(1, 8)
    local hits = tonumber(entry.hitCount) or 0
    local last = tostring(entry.lastAccessedAt or ""):sub(1, 10)
    local desc = tostring(entry.description or ""):gsub("\n", " ")
    if width and #desc > width then desc = desc:sub(1, width - 3) .. "..." end
    return string.format("[H:%3d] %-30s %-8s %s  %s", hits, name, mtype, last, desc)
end

M._sort_entries = sort_entries
M._format_label = format_label

local function open_file(name)
    local cwd = vim.fn.getcwd()
    local candidates = {
        cwd .. "/.poor-cli/memory/" .. name .. ".md",
        cwd .. "/.poor-cli/memory/" .. name,
        vim.fn.expand("~/.poor-cli/memory/" .. name .. ".md"),
        vim.fn.expand("~/.poor-cli/memory/" .. name),
    }
    for _, p in ipairs(candidates) do
        if vim.fn.filereadable(p) == 1 then
            vim.cmd("edit " .. vim.fn.fnameescape(p))
            return true
        end
    end
    require("poor-cli.notify").notify("[poor-cli] memory file not found: " .. name, vim.log.levels.WARN)
    return false
end

local function present(entries)
    local mode = M.sort_modes[M._mode_idx]
    local sorted = sort_entries(entries, mode)
    local width = math.max(40, math.floor(vim.o.columns * 0.4))
    local labels = {}
    for i, e in ipairs(sorted) do labels[i] = format_label(e, width) end
    local prompt = string.format("poor-cli memory [sort=%s — 's' to cycle]", mode)
    vim.ui.select(labels, { prompt = prompt }, function(_, idx)
        if not idx then return end
        local picked = sorted[idx]
        if not picked then return end
        open_file(picked.name or picked.filename or "")
    end)
end

function M.cycle_sort()
    M._mode_idx = (M._mode_idx % #M.sort_modes) + 1
    return M.sort_modes[M._mode_idx]
end

function M.open()
    local rpc = require("poor-cli.rpc")
    rpc.request("poor-cli/memoryList", {}, function(result, err)
        vim.schedule(function()
            if err then
                require("poor-cli.notify").notify("[poor-cli] memoryList: " .. rpc.format_error(err), vim.log.levels.ERROR)
                return
            end
            local entries = (result or {}).memories or {}
            if #entries == 0 then
                require("poor-cli.notify").notify("[poor-cli] no memories", vim.log.levels.INFO)
                return
            end
            present(entries)
        end)
    end)
end

-- setup() intentionally removed: picker opens via `:PoorCLIMemory list` and sort
-- cycles via `:PoorCLIMemory sort`. M.open() and M.cycle_sort() remain as the
-- module API called by the memory dispatcher.
function M.setup() end

return M

-- poor-cli/ux/panels_bulk.lua
-- :PoorCLIPanels {open|close|toggle} [name...]
-- bulk open/close/toggle of registered panels.

local M = {}

local function registry()
    local ok, panels = pcall(require, "poor-cli.panels")
    if not ok or type(panels.panels) ~= "table" then return {} end
    return panels.panels
end

local function selected(names)
    local reg = registry()
    if #names == 0 then return reg end
    local sel = {}
    for _, n in ipairs(names) do
        if reg[n] then sel[n] = reg[n] end
    end
    return sel
end

function M.open(names)
    for _, p in pairs(selected(names or {})) do
        pcall(p.open)
    end
end

function M.close(names)
    for _, p in pairs(selected(names or {})) do
        pcall(p.close)
    end
end

function M.toggle(names)
    for _, p in pairs(selected(names or {})) do
        pcall(p.toggle)
    end
end

function M.install()
    pcall(vim.api.nvim_del_user_command, "PoorCLIPanels")
    vim.api.nvim_create_user_command("PoorCLIPanels", function(opts)
        local args = vim.split(opts.args or "", "%s+")
        local action = args[1] or "toggle"
        local names = {}
        for i = 2, #args do if args[i] ~= "" then table.insert(names, args[i]) end end
        if action == "open" then M.open(names)
        elseif action == "close" then M.close(names)
        elseif action == "toggle" then M.toggle(names)
        else
            require("poor-cli.notify").notify("[poor-cli] usage: :PoorCLIPanels {open|close|toggle} [name...]", vim.log.levels.WARN)
        end
    end, {
        nargs = "*",
        desc = "Bulk panel control",
        complete = function(_, line)
            local parts = vim.split(line, "%s+")
            if #parts <= 2 then return { "open", "close", "toggle" } end
            local names = {}
            for n, _ in pairs(registry()) do table.insert(names, n) end
            return names
        end,
    })
end

return M

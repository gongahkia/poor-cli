-- poor-cli/ux/palette.lua
-- :PoorCLIPalette — fuzzy-find over all :PoorCLI* commands

local M = {}

function M.list_commands()
    local all = vim.api.nvim_get_commands({})
    local items = {}
    for name, info in pairs(all) do
        if name:sub(1, 7) == "PoorCLI" and name:sub(1, 11) ~= "PoorCliQ" then
            table.insert(items, {
                name = name,
                desc = (info and info.definition) or "",
                nargs = info and info.nargs or "0",
            })
        end
    end
    table.sort(items, function(a, b) return a.name < b.name end)
    return items
end

function M.open()
    local items = M.list_commands()
    if #items == 0 then
        require("poor-cli.notify").notify("[poor-cli] no commands registered yet; run setup first", vim.log.levels.WARN)
        return
    end
    local labels = {}
    for i, it in ipairs(items) do
        labels[i] = string.format(":%s  — %s", it.name, it.desc ~= "" and it.desc:sub(1, 60) or "(no description)")
    end
    vim.ui.select(labels, { prompt = "poor-cli command palette" }, function(_, idx)
        if not idx then return end
        local cmd = items[idx]
        if not cmd then return end
        if cmd.nargs == "0" then
            vim.cmd(cmd.name)
        else
            local args = vim.fn.input(":" .. cmd.name .. " ")
            if args == nil then return end
            vim.cmd(cmd.name .. " " .. args)
        end
    end)
end

function M.install()
    pcall(vim.api.nvim_del_user_command, "PoorCLIPalette")
    vim.api.nvim_create_user_command("PoorCLIPalette", function() M.open() end, { desc = "poor-cli command palette" })
end

return M

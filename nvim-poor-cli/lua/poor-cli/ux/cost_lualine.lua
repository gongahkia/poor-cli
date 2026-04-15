-- poor-cli/ux/cost_lualine.lua
-- Auto-register the cost component in the user's active lualine config
-- when their sections don't already include it.

local M = {}

local function already_present(section)
    if type(section) ~= "table" then return false end
    for _, entry in ipairs(section) do
        if type(entry) == "string" and entry:find("poor%-cli") then return true end
        if type(entry) == "table" and type(entry[1]) == "string" and entry[1]:find("poor%-cli") then return true end
        if type(entry) == "function" then
            -- can't introspect; skip
        end
    end
    return false
end

function M.install()
    local ok, lualine = pcall(require, "lualine")
    if not ok then return false end
    local cfg = lualine.get_config()
    cfg.sections = cfg.sections or {}
    cfg.sections.lualine_y = cfg.sections.lualine_y or {}
    if not already_present(cfg.sections.lualine_y) and not already_present(cfg.sections.lualine_x) then
        table.insert(cfg.sections.lualine_y, 1, require("poor-cli.lualine").component_cost)
        lualine.setup(cfg)
    end
    return true
end

return M

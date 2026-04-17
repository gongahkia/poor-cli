-- poor-cli/onboarding.lua
-- First-run onboarding facade. The 9-step render/nav machinery has been
-- replaced by a linear vim.ui.select/input chain driven by onboarding/run.lua.
-- Step descriptors live in onboarding/steps.lua; state persistence lives in
-- milestones.lua.

local config = require("poor-cli.config")
local milestones = require("poor-cli.onboarding_milestones")

local M = {}

local ONBOARDING_VERSION = 1

local function marker_path()
    return vim.fs.joinpath(config.get_state_dir(), "onboarding_version")
end

function M.should_show()
    local state = milestones.load_state()
    if state.dismissed == true or state.completed == true then return false end
    local f = io.open(marker_path(), "r")
    if not f then return true end
    local ver = tonumber(f:read("*a"))
    f:close()
    return not ver or ver < ONBOARDING_VERSION
end

function M.mark_complete()
    local state = milestones.load_state()
    state.completed = true
    state.dismissed = true
    state.onboarding_version = ONBOARDING_VERSION
    milestones.save_state(state)
    local f = io.open(marker_path(), "w")
    if f then f:write(tostring(ONBOARDING_VERSION)); f:close() end
end

function M.open()
    local run = require("poor-cli.onboarding.run")
    local steps = require("poor-cli.onboarding.steps").STEPS
    run.run(steps, function() M.mark_complete() end)
end

function M.open_tour()
    local run = require("poor-cli.onboarding.run")
    local steps = require("poor-cli.onboarding.steps").TOUR_STEPS
    run.run(steps)
end

function M.close() end -- backwards-compat no-op: no persistent wizard buffer anymore.

-- Config cheatsheet export — unchanged public API.
local function encode_lua(value, indent)
    indent = indent or 0
    local pad = string.rep("  ", indent)
    if type(value) == "table" then
        if vim.tbl_isempty(value) then return "{}" end
        local parts = { "{" }
        local is_array = vim.islist and vim.islist(value) or value[1] ~= nil
        if is_array then
            for _, v in ipairs(value) do
                table.insert(parts, pad .. "  " .. encode_lua(v, indent + 1) .. ",")
            end
        else
            for k, v in pairs(value) do
                table.insert(parts, pad .. "  " .. tostring(k) .. " = " .. encode_lua(v, indent + 1) .. ",")
            end
        end
        table.insert(parts, pad .. "}")
        return table.concat(parts, "\n")
    end
    if type(value) == "string" then return string.format("%q", value) end
    if type(value) == "boolean" or type(value) == "number" then return tostring(value) end
    return "nil"
end

function M.cheatsheet_lines()
    return vim.split("require('poor-cli').setup(" .. encode_lua(config.config or {}, 0) .. ")", "\n", { plain = true })
end

function M.export_cheatsheet()
    local float_win = require("poor-cli.float_win")
    float_win.open_lines(M.cheatsheet_lines(), {
        filetype = "lua",
        name = "[poor-cli config cheatsheet]",
        title = " config cheatsheet ",
        width = 0.7,
        height = 0.6,
        position = "center",
    })
end

local function open_arg(arg)
    if arg == "tour" then M.open_tour(); return end
    M.open()
end

function M.setup()
    milestones.setup()
    vim.keymap.set("n", "<leader>po?", M.export_cheatsheet,
        { desc = "Export poor-cli config cheatsheet" })
end

M._open_arg = open_arg

return M

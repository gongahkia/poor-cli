local config = require("poor-cli.config")

local M = {}

M.min_interval_s = 3600
M.milestones = {
    { id = "completion_accept_5", event = "completions", threshold = 5, suggestion = "Tip: use <C-Right> to accept one word from an inline completion." },
    { id = "turns_10_plan", event = "turns", threshold = 10, suggestion = "Tip: try Plan Mode with :PoorCLIPlan open before broad edits." },
    { id = "diff_review_1", event = "diffs_reviewed", threshold = 1, suggestion = "Tip: reopen staged edits with :PoorCLIDiff review; ga/gr reviews one hunk." },
    { id = "turns_25_context", event = "turns", threshold = 25, suggestion = "Tip: inspect included files with :PoorCLIContext show before long prompts." },
}

function M.state_path()
    return vim.fs.joinpath(config.get_state_dir(), "onboarding.json")
end

local function defaults()
    return {
        version = 1,
        completed = false,
        dismissed = false,
        tour_completed = false,
        do_not_nag = false,
        counters = {},
        seen_tips = {},
        last_tip_at = 0,
    }
end

local function decode(text)
    local ok, data = pcall(vim.json and vim.json.decode or vim.fn.json_decode, text)
    if ok and type(data) == "table" then return data end
    return {}
end

function M.load_state()
    local state = defaults()
    local f = io.open(M.state_path(), "r")
    if f then
        state = vim.tbl_deep_extend("force", state, decode(f:read("*a")))
        f:close()
    end
    state.counters = type(state.counters) == "table" and state.counters or {}
    state.seen_tips = type(state.seen_tips) == "table" and state.seen_tips or {}
    if state.doNotNag == true then state.do_not_nag = true end
    return state
end

function M.save_state(state)
    vim.fn.mkdir(config.get_state_dir(), "p")
    local f = io.open(M.state_path(), "w")
    if not f then return false end
    f:write((vim.json and vim.json.encode or vim.fn.json_encode)(state or defaults()))
    f:close()
    return true
end

local function fire_tip(tip, opts)
    opts = opts or {}
    if opts.notify then
        opts.notify(tip)
        return
    end
    vim.schedule(function()
        require("poor-cli.notify").notify("[poor-cli] " .. tip.suggestion, vim.log.levels.INFO)
    end)
end

function M.next_tip(state, event)
    for _, tip in ipairs(M.milestones) do
        if tip.event == event
            and (state.counters[event] or 0) >= tip.threshold
            and state.seen_tips[tip.id] ~= true then
            return tip
        end
    end
    return nil
end

function M.record_event(event, amount, opts)
    opts = opts or {}
    amount = amount or 1
    local state = M.load_state()
    state.counters[event] = (state.counters[event] or 0) + amount
    if state.do_not_nag == true then
        M.save_state(state)
        return nil
    end
    local tip = M.next_tip(state, event)
    if tip then
        local now = opts.now or os.time()
        local cooldown = opts.cooldown_s or M.min_interval_s
        if opts.force or (now - (state.last_tip_at or 0)) >= cooldown then
            state.seen_tips[tip.id] = true
            state.last_tip_at = now
            M.save_state(state)
            fire_tip(tip, opts)
            return tip
        end
    end
    M.save_state(state)
    return nil
end

function M.set_do_not_nag(value)
    local state = M.load_state()
    state.do_not_nag = value == true
    return M.save_state(state)
end

function M.setup(opts)
    opts = opts or {}
    if opts.min_interval_s then M.min_interval_s = opts.min_interval_s end
    local group = vim.api.nvim_create_augroup("poor-cli-onboarding-milestones", { clear = true })
    vim.api.nvim_create_autocmd("User", {
        group = group,
        pattern = "PoorCLICompletionAccepted",
        callback = function() M.record_event("completions") end,
    })
    vim.api.nvim_create_autocmd("User", {
        group = group,
        pattern = "PoorCLITurnEnded",
        callback = function() M.record_event("turns") end,
    })
    vim.api.nvim_create_autocmd("User", {
        group = group,
        pattern = "PoorCLIEditCommitted",
        callback = function() M.record_event("diffs_reviewed") end,
    })
end

return M

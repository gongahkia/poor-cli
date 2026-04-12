local M = {}

local function normalize_outcome(raw)
    local outcome = tostring(raw or ""):lower()
    if outcome == "ask" then return "prompt" end
    if outcome == "allow" or outcome == "deny" or outcome == "prompt" then return outcome end
    return "prompt"
end

function M.flatten_rules(rules)
    local out = {}
    if type(rules) ~= "table" then return out end
    if rules[1] ~= nil then
        for _, rule in ipairs(rules) do
            if type(rule) == "table" then table.insert(out, rule) end
        end
        return out
    end
    for scope, scoped in pairs(rules) do
        if type(scoped) == "table" then
            for _, rule in ipairs(scoped) do
                if type(rule) == "table" then
                    local copy = vim.deepcopy(rule)
                    copy.scope = copy.scope or scope
                    table.insert(out, copy)
                end
            end
        end
    end
    return out
end

function M.counts(rules)
    local counts = { allow = 0, deny = 0, prompt = 0, total = 0 }
    for _, rule in ipairs(M.flatten_rules(rules)) do
        local outcome = normalize_outcome(rule.outcome or rule.behavior)
        counts[outcome] = (counts[outcome] or 0) + 1
        counts.total = counts.total + 1
    end
    return counts
end

function M.render_counts(counts)
    counts = counts or {}
    return string.format(
        "allow=%d deny=%d prompt=%d",
        tonumber(counts.allow) or 0,
        tonumber(counts.deny) or 0,
        tonumber(counts.prompt) or 0
    )
end

function M.summary_line(rules_or_counts)
    local counts = rules_or_counts or {}
    if counts.total == nil then counts = M.counts(rules_or_counts) end
    return M.render_counts(counts)
end

return M

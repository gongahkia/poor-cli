local rpc = require("poor-cli.rpc")

local M = {}

local function s(value)
    return tostring(value or "")
end

local function normalize_threshold(threshold)
    local value = s(threshold):lower():gsub("%s+", "_")
    return value
end

local function normalize_status(status)
    return s(status or "pending"):lower()
end

local function display_name(vote)
    local value = s(vote.displayName or vote.display_name or vote.name or vote.connectionId or vote.connection_id):gsub("\n", " ")
    return value
end

local function vote_decision(vote)
    return s(vote.decision or vote.vote):lower()
end

local function sorted_votes(votes)
    if type(votes) ~= "table" then return {} end
    if #votes > 0 then return votes end
    local rows = {}
    for key, vote in pairs(votes) do
        if type(vote) == "table" then
            if not vote.connectionId and not vote.connection_id then vote.connectionId = key end
            table.insert(rows, vote)
        end
    end
    table.sort(rows, function(a, b) return display_name(a) < display_name(b) end)
    return rows
end

local function names_for(votes, decision)
    local names = {}
    for _, vote in ipairs(sorted_votes(votes)) do
        if vote_decision(vote) == decision then table.insert(names, display_name(vote)) end
    end
    return names
end

function M.render_vote_row(hunk_id, votes, status, threshold)
    local vote_threshold = normalize_threshold(threshold)
    if vote_threshold == "owner_only" then return {} end

    local approved = names_for(votes, "approve")
    local rejected = names_for(votes, "reject")
    local parts = {}
    if #approved > 0 then table.insert(parts, "✓ " .. table.concat(approved, ", ")) end
    if #rejected > 0 then table.insert(parts, "✗ " .. table.concat(rejected, ", ")) end
    if #parts == 0 then table.insert(parts, "none") end

    local state = normalize_status(status)
    local suffix = state
    if vote_threshold ~= "" then suffix = suffix .. " (" .. vote_threshold .. ")" end
    table.insert(parts, suffix)
    return { "votes: " .. table.concat(parts, " · ") }
end

function M.vote(hunk_id, decision, edit_id, callback)
    if type(edit_id) == "function" then
        callback = edit_id
        edit_id = nil
    end
    local params = { hunkId = hunk_id, decision = decision }
    if edit_id and edit_id ~= "" then params.editId = edit_id end
    rpc.request("poor-cli/voteOnHunk", params, callback)
    return true
end

return M

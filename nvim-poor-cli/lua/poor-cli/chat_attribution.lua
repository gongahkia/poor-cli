local M = {}

local function trim(value)
    return tostring(value or ""):gsub("^%s+", ""):gsub("%s+$", "")
end

local function clean_name(value)
    local name = trim(value):gsub("[%c\r\n]", " ")
    name = name:gsub("%s+", " ")
    return trim(name)
end

local function member_id(member)
    if type(member) ~= "table" then return "" end
    return trim(member.connectionId or member.connection_id or member.id)
end

local function member_name(member)
    if type(member) ~= "table" then return "" end
    return clean_name(member.displayName or member.display_name or member.name or member_id(member))
end

function M.format_author(event)
    if type(event) ~= "table" then
        return ""
    end
    local name = clean_name(event.authorDisplayName or event.author_display_name)
    if name == "" then
        name = clean_name(event.authorConnectionId or event.author_connection_id)
    end
    if name == "" then
        return ""
    end
    return name .. " ›"
end

local function local_connection_id(snapshot)
    return trim(snapshot.localConnectionId or snapshot.local_connection_id or snapshot.localId or snapshot.local_id)
end

local function collect_members(snapshot)
    local names = {}
    local order = {}
    local members = snapshot.members
    if type(members) ~= "table" then
        return names, order
    end
    for key, member in pairs(members) do
        local id = member_id(member)
        if id == "" and type(key) == "string" then id = key end
        if id ~= "" then
            names[id] = member_name(member)
            table.insert(order, id)
        end
    end
    table.sort(order)
    if #members > 0 then
        order = {}
        for _, member in ipairs(members) do
            local id = member_id(member)
            if id ~= "" then
                names[id] = member_name(member)
                table.insert(order, id)
            end
        end
    end
    return names, order
end

function M.format_typing_footer(presence_snapshot)
    if type(presence_snapshot) ~= "table" then
        return nil
    end
    local presence = presence_snapshot.presence or presence_snapshot.typing or presence_snapshot
    if type(presence) ~= "table" then
        return nil
    end
    local local_id = local_connection_id(presence_snapshot)
    local names, order = collect_members(presence_snapshot)
    local seen = {}
    local typers = {}
    local function add(id)
        id = trim(id)
        if id == "" or id == local_id or seen[id] then return end
        seen[id] = true
        table.insert(typers, names[id] or clean_name(id))
    end
    for _, id in ipairs(order) do
        if presence[id] == true then add(id) end
    end
    local rest = {}
    for id, typing in pairs(presence) do
        if typing == true and type(id) == "string" then table.insert(rest, id) end
    end
    table.sort(rest)
    for _, id in ipairs(rest) do add(id) end
    if #typers == 0 then
        return nil
    end
    if #typers == 1 then
        return typers[1] .. " is typing…"
    end
    if #typers == 2 then
        return typers[1] .. " and " .. typers[2] .. " are typing…"
    end
    return table.concat(typers, ", ", 1, #typers - 1) .. ", and " .. typers[#typers] .. " are typing…"
end

return M

local M = {}

function M.parse(diff_text)
    local hunks = {}
    local current = nil
    for line in (tostring(diff_text or "") .. "\n"):gmatch("(.-)\n") do
        if line == "" and current == nil then goto continue end
        if line:match("^@@") then
            current = {
                hunk_id = tostring(#hunks + 1),
                header = line,
                before = {},
                after = {},
                line_start = tonumber(line:match("^@@ %-(%d+)")) or 1,
            }
            table.insert(hunks, current)
        elseif current then
            local prefix = line:sub(1, 1)
            if prefix == "-" and not line:match("^%-%-%-") then
                table.insert(current.before, line:sub(2))
            elseif prefix == "+" and not line:match("^%+%+%+") then
                table.insert(current.after, line:sub(2))
            elseif prefix == " " then
                table.insert(current.before, line:sub(2))
                table.insert(current.after, line:sub(2))
            end
        end
        ::continue::
    end
    return { hunks = hunks }
end

return M

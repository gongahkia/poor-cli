local root = vim.fn.fnamemodify(debug.getinfo(1, "S").source:sub(2), ":p:h:h")
package.path = root .. "/lua/?.lua;" .. root .. "/lua/?/init.lua;" .. package.path

describe("users panel", function()
    local panel
    local calls
    local host
    local presence
    local queue

    local function wait()
        vim.wait(100, function() return false end, 10)
    end

    local function install_rpc()
        package.loaded["poor-cli.rpc"] = {
            get_multiplayer_state = function()
                return { enabled = true, room = "dev" }
            end,
            request = function(method, params, cb)
                table.insert(calls, { method = method, params = vim.deepcopy(params or {}) })
                if method == "poor-cli/listHostMembers" then cb(vim.deepcopy(host), nil)
                elseif method == "poor-cli/listPresence" then cb(vim.deepcopy(presence), nil)
                elseif method == "poor-cli/listRoomQueue" then cb(vim.deepcopy(queue), nil)
                else cb({ success = true }, nil) end
            end,
            format_error = function(err) return tostring(err and err.message or err) end,
        }
    end

    before_each(function()
        calls = {}
        host = {
            rooms = {{
                name = "dev",
                activeConnectionId = "c1",
                members = {
                    { connectionId = "c1", displayName = "Ada", role = "prompter", approved = true, approvalState = "approved", uiRole = "driver" },
                    { connectionId = "c2", displayName = "Ben", role = "viewer", approved = true, approvalState = "approved" },
                    { connectionId = "c3", displayName = "Cam", role = "viewer", approved = false, approvalState = "pending" },
                },
                viewerInviteLink = "viewer-link",
                prompterInviteLink = "prompter-link",
            }},
        }
        host.room = host.rooms[1]
        presence = { room = "dev", presence = { c1 = true }, members = { { connectionId = "c1", displayName = "Ada", typing = true } } }
        queue = { room = "dev", snapshot = { { queueId = "q1", connectionId = "c2", position = 3 } } }
        install_rpc()
        package.loaded["poor-cli.config"] = { is_debug = function() return false end }
        package.loaded["poor-cli.notify"] = { notify = function() end }
        package.loaded["poor-cli.users_panel"] = nil
        panel = require("poor-cli.users_panel")
        panel.setup()
    end)

    after_each(function()
        if panel then pcall(panel.close) end
        for _, buf in ipairs(vim.api.nvim_list_bufs()) do
            if vim.api.nvim_buf_is_valid(buf) and vim.api.nvim_buf_get_name(buf):match("%[poor%-cli users%]") then
                pcall(vim.api.nvim_buf_delete, buf, { force = true })
            end
        end
        package.loaded["poor-cli.rpc"] = nil
        package.loaded["poor-cli.config"] = nil
        package.loaded["poor-cli.notify"] = nil
        package.loaded["poor-cli.users_panel"] = nil
    end)

    it("opens with golden render", function()
        local buf = panel.open()
        wait()
        local text = table.concat(vim.api.nvim_buf_get_lines(buf, 0, -1, false), "\n")
        assert.are.equal(table.concat({
            "users (3)",
            "────────────────────────────────",
            ">Ada          prompter ← driver",
            "              ● typing…",
            "·Ben          viewer   approved",
            "              #3 in queue",
            "·Cam          viewer   pending",
            "              [a]approve [d]deny",
        }, "\n"), text)
    end)

    it("updates typing row from notification", function()
        local buf = panel.open()
        wait()
        vim.api.nvim_exec_autocmds("User", {
            pattern = "PoorCLIMemberTyping",
            data = { connection_id = "c2", display_name = "Ben", typing = true },
        })
        local text = table.concat(vim.api.nvim_buf_get_lines(buf, 0, -1, false), "\n")
        assert.truthy(text:find("·Ben          viewer   approved", 1, true))
        assert.truthy(text:find("              ● typing…", 1, true))
    end)

    it("approves focused pending member with keymap", function()
        local buf = panel.open()
        wait()
        vim.api.nvim_set_current_win(panel.win)
        vim.api.nvim_win_set_cursor(panel.win, { 7, 0 })
        vim.api.nvim_feedkeys("a", "x", false)
        wait()
        local found = false
        for _, call in ipairs(calls) do
            if call.method == "poor-cli/approveHostMember" and call.params.connectionId == "c3" then found = true end
        end
        assert.truthy(found)
    end)

    it("closes without refreshing on notifications", function()
        panel.open()
        wait()
        panel.close()
        local before = #calls
        vim.api.nvim_exec_autocmds("User", {
            pattern = "PoorCLICollabMemberJoined",
            data = { room = "dev", connectionId = "c4" },
        })
        vim.api.nvim_exec_autocmds("User", {
            pattern = "PoorCLIQueueUpdated",
            data = { room = "dev", snapshot = { { connectionId = "c2", position = 1 } } },
        })
        wait()
        assert.are.equal(before, #calls)
        assert.falsy(panel.win and vim.api.nvim_win_is_valid(panel.win))
    end)
end)

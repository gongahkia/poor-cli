local root = vim.fn.fnamemodify(debug.getinfo(1, "S").source:sub(2), ":p:h:h")
package.path = root .. "/lua/?.lua;" .. root .. "/lua/?/init.lua;" .. package.path

describe("multiplayer room", function()
    local room
    local calls
    local snapshot

    local function wait()
        vim.wait(100, function() return false end, 10)
    end

    before_each(function()
        calls = {}
        snapshot = {
            room = {
                name = "dev",
                inviteLink = "poor-cli --remote-invite abc",
                activeConnectionId = "c1",
                members = {
                    { connectionId = "c1", displayName = "Ada", role = "prompter", uiRole = "driver" },
                    { connectionId = "c2", displayName = "Lin", role = "viewer", uiRole = "navigator", handRaised = true, queuePosition = 1 },
                },
            },
            rooms = {},
        }
        snapshot.rooms = { snapshot.room }
        package.loaded["poor-cli.config"] = {
            get = function(key)
                if key == "multiplayer" then return { enabled = true } end
                return nil
            end,
        }
        package.loaded["poor-cli.rpc"] = {
            get_multiplayer_state = function()
                return { enabled = true, room = "dev", active_connection_id = "c1", members = snapshot.room.members }
            end,
            request = function(method, params, cb)
                table.insert(calls, { method = method, params = params })
                if method == "collab.room" then cb(snapshot, nil) else cb({ success = true }, nil) end
            end,
            peer_message = function(text, cb)
                table.insert(calls, { method = "poor-cli/peerMessage", text = text })
                cb({ success = true }, nil)
            end,
            format_error = function(err) return tostring(err and err.message or err) end,
        }
        package.loaded["poor-cli.multiplayer_room"] = nil
        room = require("poor-cli.multiplayer_room")
    end)

    after_each(function()
        for _, buf in ipairs(vim.api.nvim_list_bufs()) do
            if vim.api.nvim_buf_is_valid(buf) and vim.api.nvim_buf_get_name(buf):match("%[poor-cli multiplayer room%]") then
                pcall(vim.api.nvim_buf_delete, buf, { force = true })
            end
        end
        package.loaded["poor-cli.config"] = nil
        package.loaded["poor-cli.rpc"] = nil
        package.loaded["poor-cli.multiplayer_room"] = nil
    end)

    it("test_members_rendered_with_roles", function()
        local text = table.concat(room.render_lines(snapshot), "\n")
        assert.truthy(text:find("Ada [prompter]", 1, true))
        assert.truthy(text:find("Lin [viewer]", 1, true))
        assert.truthy(text:find("host [owner]", 1, true))
    end)

    it("test_pass_driver_updates_indicator", function()
        room.pass_driver("c2")
        wait()
        assert.are.equal("collab.room/pass_driver", calls[#calls].method)
        assert.are.equal("c2", calls[#calls].params.connectionId)
    end)

    it("test_hand_raised_appears_in_queue", function()
        local text = table.concat(room.render_lines(snapshot), "\n")
        assert.truthy(text:find("[Grant] Lin c2", 1, true))
    end)

    it("copies invite link", function()
        room.open()
        wait()
        room.copy_invite()
        assert.truthy(vim.fn.getreg("+") == "poor-cli --remote-invite abc" or vim.fn.getreg('"') == "poor-cli --remote-invite abc")
    end)
end)

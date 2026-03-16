local poor_cli = require("poor-cli")

describe("poor-cli setup and commands", function()
    after_each(function()
        _G.test_helpers.cleanup()
    end)

    it("should be safe to run setup multiple times", function()
        assert.has_no.errors(function()
            poor_cli.setup({
                auto_start = false,
                check_health_on_setup = false,
            })
            poor_cli.setup({
                auto_start = false,
                check_health_on_setup = false,
            })
        end)

        assert.are.equal(2, vim.fn.exists(":PoorCliDoctor"))
        assert.are.equal(2, vim.fn.exists(":PoorCliCancel"))
        assert.are.equal(2, vim.fn.exists(":PoorCliRestart"))
        assert.are.equal(2, vim.fn.exists(":PoorCliWriteMinInit"))
    end)
end)

local M = {}

function M.extend(deps)
    local spec = deps.spec
    local rpc = deps.rpc
    local chat = deps.chat
    local notify = deps.notify
    local open_scratch = deps.open_scratch

    spec.extend("review", {
        verb_names = { "file", "pr", "commit", "lint" },
        verbs = {
            file = function(fargs)
                local target = fargs[1]
                local prompt = target
                    and ("Review the file " .. target .. " for issues, improvements, and best practices.")
                    or "Review the current staged git diff for issues, improvements, and best practices. Use git_diff to inspect changes."
                chat.open()
                rpc.request("poor-cli/chat", { message = prompt }, function(result, err) vim.schedule(function()
                    if err then
                        chat.append_message("assistant", "Error: " .. rpc.format_error(err))
                    elseif result and result.content then
                        chat.append_message("user", target and ("Review " .. target) or "Review staged diff")
                        chat.append_message("assistant", result.content)
                    end
                end) end)
            end,
            pr = function(fargs)
                local num = fargs[1]
                if not num or num == "" then notify("usage: :PoorCLIReview pr <pr_number>", vim.log.levels.WARN); return end
                notify("reviewing PR #" .. num .. "...", vim.log.levels.INFO)
                rpc.request("poor-cli/chat", { message = "/review-pr " .. num }, function(result, err) vim.schedule(function()
                    if err then notify(rpc.format_error(err), vim.log.levels.ERROR); return end
                    if result and result.content then open_scratch("[poor-cli PR #" .. num .. " review]", result.content) end
                end) end)
            end,
            commit = function()
                chat.open()
                rpc.request("poor-cli/chat", {
                    message = "Generate a concise, conventional commit message for the currently staged git changes. "
                        .. "Use git_diff and git_status to inspect the staged changes. Output ONLY the commit message.",
                }, function(result, err) vim.schedule(function()
                    if err then
                        chat.append_message("assistant", "Error: " .. rpc.format_error(err))
                    elseif result and result.content then
                        chat.append_message("user", "Generate commit message")
                        chat.append_message("assistant", result.content)
                        pcall(function() require("poor-cli.integrations.neogit").open_for_commit(result.content) end)
                    end
                end) end)
            end,
            lint = function()
                rpc.request("poor-cli/chat", { message = "/lint" }, function(result, err) vim.schedule(function()
                    if err then notify(rpc.format_error(err), vim.log.levels.ERROR); return end
                    if result and result.content then open_scratch("[poor-cli lint]", result.content) end
                end) end)
            end,
            ["diff-compare"] = function(fargs)
                if #fargs < 2 then notify("usage: :PoorCLIReview diff-compare <file1> <file2>", vim.log.levels.WARN); return end
                local result, err = rpc.compare_files(fargs[1], fargs[2], 15000)
                if err then notify(rpc.format_error(err), vim.log.levels.ERROR); return end
                local diff_text = type(result) == "table" and (result.diff or vim.inspect(result)) or tostring(result)
                open_scratch("[poor-cli diff]", diff_text, "diff")
            end,
            diff = function() require("poor-cli.diff_review").open() end,
            ["diff-close"] = function() require("poor-cli.diff_review").close() end,
            ["diff-layout"] = function() require("poor-cli.diff_review").toggle_layout() end,
            timeline = function() require("poor-cli.timeline").toggle() end,
            ["timeline-cancel"] = function() require("poor-cli.timeline").cancel_current() end,
        },
    })
end

return M

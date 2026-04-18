local M = {}

function M.extend(deps)
    local spec = deps.spec
    local rpc = deps.rpc
    local notify = deps.notify
    local open_scratch = deps.open_scratch
    local build_context_text = deps.build_context_text

    spec.extend("context", {
        verb_prefix = "search-",
        verbs = {
            run = function(fargs)
                local q = table.concat(fargs, " ")
                if q == "" then notify("usage: :PoorCLIContext search <query>", vim.log.levels.WARN); return end
                rpc.hybrid_search(q, 20, function(result, err) vim.schedule(function()
                    if err then notify(rpc.format_error(err), vim.log.levels.ERROR); return end
                    local results = (result or {}).results or result or {}
                    local lines = { "# search: " .. q, "" }
                    for i, r in ipairs(results) do
                        local path = r.path or r.file or "?"
                        local score = r.score and string.format(" (%.2f)", r.score) or ""
                        table.insert(lines, string.format("%d. `%s`%s", i, path, score))
                        if r.snippet or r.content then table.insert(lines, "   " .. (r.snippet or r.content):sub(1, 120)) end
                    end
                    if #results == 0 then table.insert(lines, "no results") end
                    open_scratch("[poor-cli search]", table.concat(lines, "\n"))
                end) end)
            end,
            index = function()
                notify("indexing codebase...", vim.log.levels.INFO)
                rpc.index_codebase(function(result, err) vim.schedule(function()
                    if err then notify(rpc.format_error(err), vim.log.levels.ERROR); return end
                    local stats = result or {}
                    notify(string.format("indexed: %s files, %s chunks",
                        tostring(stats.total_files or stats.totalFiles or "?"),
                        tostring(stats.total_chunks or stats.totalChunks or "?")), vim.log.levels.INFO)
                end) end)
            end,
            stats = function()
                local result, err = rpc.get_index_stats(10000)
                if err then notify(rpc.format_error(err), vim.log.levels.ERROR); return end
                local r = type(result) == "table" and result or {}
                local lines = { "# index stats", "" }
                for k, v in pairs(r) do
                    table.insert(lines, string.format("- %s: %s", tostring(k), tostring(v)))
                end
                if #lines == 2 then table.insert(lines, tostring(result)) end
                open_scratch("[poor-cli index stats]", table.concat(lines, "\n"), "markdown")
            end,
            embeddings = function()
                notify("indexing embeddings...", vim.log.levels.INFO)
                rpc.request("poor-cli/indexEmbeddings", { force = false }, function(result, err) vim.schedule(function()
                    if err then notify(rpc.format_error(err), vim.log.levels.ERROR); return end
                    notify("embeddings indexed: " .. vim.inspect(result or {}), vim.log.levels.INFO)
                end) end)
            end,
            watch = function() require("poor-cli.watch_panel").open() end,
            ["watch-scan"] = function()
                rpc.watch_scan(function(result, err) vim.schedule(function()
                    if err then notify(rpc.format_error(err), vim.log.levels.ERROR); return end
                    local items = type(result) == "table" and result or {}
                    if #items == 0 then notify("no inline instructions found", vim.log.levels.INFO); return end
                    local lines = { "# inline instructions found", "" }
                    for _, item in ipairs(items) do table.insert(lines, "- " .. vim.inspect(item)) end
                    open_scratch("[poor-cli watch]", table.concat(lines, "\n"), "markdown")
                end) end)
            end,
        },
    })

    spec.extend("context", {
        verbs = {
            search = function(fargs)
                local q = table.concat(fargs, " ")
                if q == "" then notify("usage: :PoorCLIContext search <query>", vim.log.levels.WARN); return end
                rpc.hybrid_search(q, 20, function(result, err) vim.schedule(function()
                    if err then notify(rpc.format_error(err), vim.log.levels.ERROR); return end
                    local results = (result or {}).results or result or {}
                    local lines = { "# search: " .. q, "" }
                    for i, r in ipairs(results) do
                        local path = r.path or r.file or "?"
                        local score = r.score and string.format(" (%.2f)", r.score) or ""
                        table.insert(lines, string.format("%d. `%s`%s", i, path, score))
                        if r.snippet or r.content then table.insert(lines, "   " .. (r.snippet or r.content):sub(1, 120)) end
                    end
                    if #results == 0 then table.insert(lines, "no results") end
                    open_scratch("[poor-cli search]", table.concat(lines, "\n"))
                end) end)
            end,
        },
    })

    spec.extend("context", {
        verbs = {
            show = function() require("poor-cli.context_panel").open() end,
            ["repo-map"] = function(fargs) require("poor-cli.repo_map").open(tonumber(fargs[1])) end,
            ["compact-strategy"] = function(fargs)
                local strategy = fargs[1] or "compact"
                rpc.request("poor-cli/compactContext", { strategy = strategy }, function(result, err) vim.schedule(function()
                    if err then notify(rpc.format_error(err), vim.log.levels.ERROR)
                    else notify("Context compacted (" .. strategy .. "): " .. vim.inspect(result or {}), vim.log.levels.INFO) end
                end) end)
            end,
            explain = function() open_scratch("[poor-cli context]", build_context_text(), "markdown") end,
        },
        arg_complete = {
            ["compact-strategy"] = function() return { "auto", "compact", "gentle", "aggressive", "compress", "handoff" } end,
        },
    })
end

return M

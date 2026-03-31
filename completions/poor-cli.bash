# Bash completion for poor-cli
# Source this file or add to ~/.bashrc:
#   source /path/to/poor-cli.bash

_poor_cli_complete() {
    local cur prev cmd subcmd
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"
    cmd="${COMP_WORDS[1]}"
    subcmd="${COMP_WORDS[2]}"

    local root_commands="help version tui install install-info exec task automation github-task skills commands server telegram watch deploy preview review-pr agent checkpoint history session memory config profile trust provider doctor status policy tools mcp cost search review commit"
    local sandbox_presets="read-only review-only workspace-write full-access"
    local routing_modes="manual quality speed cheap private"
    local permission_modes="prompt auto-safe danger-full-access"

    if [[ ${COMP_CWORD} -eq 1 ]]; then
        COMPREPLY=( $(compgen -W "${root_commands}" -- "${cur}") )
        return 0
    fi

    case "${cmd}" in
        exec)
            local exec_opts="--prompt --output-format --resume --allow-tool --deny-tool --plan-only --provider --model --routing-mode --api-key --config --cwd --sandbox-preset --permission-mode --auto-approve --context-file --pinned-context-file --context-budget-tokens"
            case "${prev}" in
                --output-format)
                    COMPREPLY=( $(compgen -W "text json stream-json" -- "${cur}") )
                    return 0
                    ;;
                --routing-mode)
                    COMPREPLY=( $(compgen -W "${routing_modes}" -- "${cur}") )
                    return 0
                    ;;
                --sandbox-preset)
                    COMPREPLY=( $(compgen -W "${sandbox_presets}" -- "${cur}") )
                    return 0
                    ;;
                --permission-mode)
                    COMPREPLY=( $(compgen -W "${permission_modes}" -- "${cur}") )
                    return 0
                    ;;
                --config|--context-file|--pinned-context-file)
                    COMPREPLY=( $(compgen -f -- "${cur}") )
                    return 0
                    ;;
                --cwd)
                    COMPREPLY=( $(compgen -d -- "${cur}") )
                    return 0
                    ;;
            esac
            if [[ ${cur} == -* ]]; then
                COMPREPLY=( $(compgen -W "${exec_opts}" -- "${cur}") )
            fi
            return 0
            ;;

        task)
            local task_subcommands="create list show start wait approve cancel retry replay run"
            if [[ ${COMP_CWORD} -eq 2 ]]; then
                COMPREPLY=( $(compgen -W "${task_subcommands}" -- "${cur}") )
                return 0
            fi
            case "${subcmd}" in
                create)
                    local opts="--title --prompt --preset --source --requires-approval --auto-approve --approve --auto-start --no-auto-start --provider --model --routing-mode --timezone --execution-mode --reasoning-effort --config --context-file --pinned-context-file --context-budget-tokens --wait --wait-timeout-seconds --json"
                    case "${prev}" in
                        --preset)
                            COMPREPLY=( $(compgen -W "${sandbox_presets}" -- "${cur}") )
                            return 0
                            ;;
                        --routing-mode)
                            COMPREPLY=( $(compgen -W "${routing_modes}" -- "${cur}") )
                            return 0
                            ;;
                        --execution-mode)
                            COMPREPLY=( $(compgen -W "worktree local" -- "${cur}") )
                            return 0
                            ;;
                        --reasoning-effort)
                            COMPREPLY=( $(compgen -W "low medium high" -- "${cur}") )
                            return 0
                            ;;
                        --config|--context-file|--pinned-context-file)
                            COMPREPLY=( $(compgen -f -- "${cur}") )
                            return 0
                            ;;
                    esac
                    if [[ ${cur} == -* ]]; then
                        COMPREPLY=( $(compgen -W "${opts}" -- "${cur}") )
                    fi
                    return 0
                    ;;
                list)
                    local opts="--status --inbox --json"
                    if [[ ${cur} == -* ]]; then
                        COMPREPLY=( $(compgen -W "${opts}" -- "${cur}") )
                    fi
                    return 0
                    ;;
                show)
                    local opts="--response --events --log --json"
                    if [[ ${cur} == -* ]]; then
                        COMPREPLY=( $(compgen -W "${opts}" -- "${cur}") )
                    fi
                    return 0
                    ;;
                start)
                    local opts="--wait --wait-timeout-seconds --json"
                    if [[ ${cur} == -* ]]; then
                        COMPREPLY=( $(compgen -W "${opts}" -- "${cur}") )
                    fi
                    return 0
                    ;;
                wait)
                    local opts="--timeout-seconds --json"
                    if [[ ${cur} == -* ]]; then
                        COMPREPLY=( $(compgen -W "${opts}" -- "${cur}") )
                    fi
                    return 0
                    ;;
                approve|retry|replay)
                    local opts="--no-auto-start --wait --wait-timeout-seconds --json"
                    if [[ ${cur} == -* ]]; then
                        COMPREPLY=( $(compgen -W "${opts}" -- "${cur}") )
                    fi
                    return 0
                    ;;
                cancel)
                    if [[ ${cur} == -* ]]; then
                        COMPREPLY=( $(compgen -W "--json" -- "${cur}") )
                    fi
                    return 0
                    ;;
                run)
                    local opts="--task-id --repo-root --config"
                    case "${prev}" in
                        --repo-root)
                            COMPREPLY=( $(compgen -d -- "${cur}") )
                            return 0
                            ;;
                        --config)
                            COMPREPLY=( $(compgen -f -- "${cur}") )
                            return 0
                            ;;
                    esac
                    if [[ ${cur} == -* ]]; then
                        COMPREPLY=( $(compgen -W "${opts}" -- "${cur}") )
                    fi
                    return 0
                    ;;
            esac
            ;;

        automation)
            local automation_subcommands="create list show enable disable run-now run-due serve history replay"
            if [[ ${COMP_CWORD} -eq 2 ]]; then
                COMPREPLY=( $(compgen -W "${automation_subcommands}" -- "${cur}") )
                return 0
            fi
            case "${subcmd}" in
                create)
                    local opts="--name --prompt --every-minutes --daily --weekly --preset --requires-approval --auto-approve --disabled --provider --model --routing-mode --timezone --execution-mode --reasoning-effort --config --context-file --pinned-context-file --context-budget-tokens --run-now --wait --wait-timeout-seconds --json"
                    case "${prev}" in
                        --preset)
                            COMPREPLY=( $(compgen -W "${sandbox_presets}" -- "${cur}") )
                            return 0
                            ;;
                        --routing-mode)
                            COMPREPLY=( $(compgen -W "${routing_modes}" -- "${cur}") )
                            return 0
                            ;;
                        --execution-mode)
                            COMPREPLY=( $(compgen -W "worktree local" -- "${cur}") )
                            return 0
                            ;;
                        --reasoning-effort)
                            COMPREPLY=( $(compgen -W "low medium high" -- "${cur}") )
                            return 0
                            ;;
                        --config|--context-file|--pinned-context-file)
                            COMPREPLY=( $(compgen -f -- "${cur}") )
                            return 0
                            ;;
                    esac
                    if [[ ${cur} == -* ]]; then
                        COMPREPLY=( $(compgen -W "${opts}" -- "${cur}") )
                    fi
                    return 0
                    ;;
                list)
                    if [[ ${cur} == -* ]]; then
                        COMPREPLY=( $(compgen -W "--enabled --disabled --json" -- "${cur}") )
                    fi
                    return 0
                    ;;
                show|enable|disable)
                    if [[ ${cur} == -* ]]; then
                        COMPREPLY=( $(compgen -W "--json" -- "${cur}") )
                    fi
                    return 0
                    ;;
                run-now|replay)
                    if [[ ${cur} == -* ]]; then
                        COMPREPLY=( $(compgen -W "--wait --wait-timeout-seconds --json" -- "${cur}") )
                    fi
                    return 0
                    ;;
                run-due)
                    if [[ ${cur} == -* ]]; then
                        COMPREPLY=( $(compgen -W "--limit --wait --wait-timeout-seconds --json" -- "${cur}") )
                    fi
                    return 0
                    ;;
                serve)
                    if [[ ${cur} == -* ]]; then
                        COMPREPLY=( $(compgen -W "--poll-seconds" -- "${cur}") )
                    fi
                    return 0
                    ;;
                history)
                    if [[ ${cur} == -* ]]; then
                        COMPREPLY=( $(compgen -W "--limit --json" -- "${cur}") )
                    fi
                    return 0
                    ;;
            esac
            ;;

        agent)
            local subcommands="start list logs result cancel run"
            if [[ ${COMP_CWORD} -eq 2 ]]; then
                COMPREPLY=( $(compgen -W "${subcommands}" -- "${cur}") )
                return 0
            fi
            case "${subcmd}" in
                start)
                    if [[ ${cur} == -* ]]; then
                        COMPREPLY=( $(compgen -W "--prompt -p --sandbox --no-worktree --max-runtime --max-cost --json" -- "${cur}") )
                    fi
                    return 0
                    ;;
                list)
                    if [[ ${cur} == -* ]]; then
                        COMPREPLY=( $(compgen -W "--status --json" -- "${cur}") )
                    fi
                    return 0
                    ;;
                logs)
                    if [[ ${cur} == -* ]]; then
                        COMPREPLY=( $(compgen -W "--tail" -- "${cur}") )
                    fi
                    return 0
                    ;;
                run)
                    if [[ ${cur} == -* ]]; then
                        COMPREPLY=( $(compgen -W "--agent-id --repo-root" -- "${cur}") )
                    fi
                    return 0
                    ;;
            esac
            ;;

        skills)
            if [[ ${COMP_CWORD} -eq 2 ]]; then
                COMPREPLY=( $(compgen -W "list show run" -- "${cur}") )
                return 0
            fi
            if [[ "${subcmd}" == "list" && ${cur} == -* ]]; then
                COMPREPLY=( $(compgen -W "--json" -- "${cur}") )
                return 0
            fi
            ;;

        commands)
            if [[ ${COMP_CWORD} -eq 2 ]]; then
                COMPREPLY=( $(compgen -W "list show run" -- "${cur}") )
                return 0
            fi
            if [[ "${subcmd}" == "list" && ${cur} == -* ]]; then
                COMPREPLY=( $(compgen -W "--json" -- "${cur}") )
                return 0
            fi
            ;;

        github-task)
            if [[ ${COMP_CWORD} -eq 2 ]]; then
                COMPREPLY=( $(compgen -W "create" -- "${cur}") )
                return 0
            fi
            if [[ "${subcmd}" == "create" ]]; then
                case "${prev}" in
                    --mode)
                        COMPREPLY=( $(compgen -W "read-only review-only" -- "${cur}") )
                        return 0
                        ;;
                    --event-path|--config|--context-file|--pinned-context-file)
                        COMPREPLY=( $(compgen -f -- "${cur}") )
                        return 0
                        ;;
                esac
                if [[ ${cur} == -* ]]; then
                    COMPREPLY=( $(compgen -W "--event-path --mode --auto-start --no-auto-start --provider --model --config --context-file --pinned-context-file --context-budget-tokens --wait --wait-timeout-seconds --json" -- "${cur}") )
                fi
                return 0
            fi
            ;;

        server)
            case "${prev}" in
                --permission-mode)
                    COMPREPLY=( $(compgen -W "${permission_modes}" -- "${cur}") )
                    return 0
                    ;;
            esac
            if [[ ${cur} == -* ]]; then
                COMPREPLY=( $(compgen -W "--stdio --host --bind --port --room --permission-mode --ngrok --bridge --invite --verbose" -- "${cur}") )
            fi
            return 0
            ;;

        telegram)
            if [[ ${COMP_CWORD} -eq 2 ]]; then
                COMPREPLY=( $(compgen -W "setup" -- "${cur}") )
                return 0
            fi
            if [[ ${cur} == -* ]]; then
                COMPREPLY=( $(compgen -W "--token --allowed-users --sandbox-preset --max-sessions --edit-interval --webhook-url --webhook-port --verbose -v --debug --log-file" -- "${cur}") )
                return 0
            fi
            ;;

        watch)
            if [[ ${cur} == -* ]]; then
                COMPREPLY=( $(compgen -W "--debounce --scan" -- "${cur}") )
            fi
            return 0
            ;;

        deploy)
            case "${prev}" in
                --target|-t)
                    COMPREPLY=( $(compgen -W "vercel netlify fly railway cloudflare" -- "${cur}") )
                    return 0
                    ;;
            esac
            if [[ ${cur} == -* ]]; then
                COMPREPLY=( $(compgen -W "--target -t --prod --list --json" -- "${cur}") )
            fi
            return 0
            ;;

        preview)
            if [[ ${cur} == -* ]]; then
                COMPREPLY=( $(compgen -W "--port --stop" -- "${cur}") )
            fi
            return 0
            ;;

        review-pr)
            if [[ ${cur} == -* ]]; then
                COMPREPLY=( $(compgen -W "--post --json --ci" -- "${cur}") )
            fi
            return 0
            ;;

        checkpoint)
            if [[ ${COMP_CWORD} -eq 2 ]]; then
                COMPREPLY=( $(compgen -W "list create preview restore" -- "${cur}") )
                return 0
            fi
            case "${subcmd}" in
                list) [[ ${cur} == -* ]] && COMPREPLY=( $(compgen -W "--limit --json" -- "${cur}") ) ;;
                create) [[ ${cur} == -* ]] && COMPREPLY=( $(compgen -W "--description -d --json" -- "${cur}") ) ;;
                preview|restore) [[ ${cur} == -* ]] && COMPREPLY=( $(compgen -W "--json" -- "${cur}") ) ;;
            esac
            return 0
            ;;

        history)
            if [[ ${COMP_CWORD} -eq 2 ]]; then
                COMPREPLY=( $(compgen -W "list search export" -- "${cur}") )
                return 0
            fi
            case "${subcmd}" in
                list) [[ ${cur} == -* ]] && COMPREPLY=( $(compgen -W "--limit --json" -- "${cur}") ) ;;
                search) [[ ${cur} == -* ]] && COMPREPLY=( $(compgen -W "--limit --json" -- "${cur}") ) ;;
                export) [[ ${cur} == -* ]] && COMPREPLY=( $(compgen -W "--output -o" -- "${cur}") ) ;;
            esac
            return 0
            ;;

        session)
            if [[ ${COMP_CWORD} -eq 2 ]]; then
                COMPREPLY=( $(compgen -W "list create fork destroy" -- "${cur}") )
                return 0
            fi
            case "${subcmd}" in
                list) [[ ${cur} == -* ]] && COMPREPLY=( $(compgen -W "--limit --json" -- "${cur}") ) ;;
                create) [[ ${cur} == -* ]] && COMPREPLY=( $(compgen -W "--label --json" -- "${cur}") ) ;;
                fork) [[ ${cur} == -* ]] && COMPREPLY=( $(compgen -W "--label --json" -- "${cur}") ) ;;
                destroy) [[ ${cur} == -* ]] && COMPREPLY=( $(compgen -W "--json" -- "${cur}") ) ;;
            esac
            return 0
            ;;

        memory)
            if [[ ${COMP_CWORD} -eq 2 ]]; then
                COMPREPLY=( $(compgen -W "list save search delete" -- "${cur}") )
                return 0
            fi
            case "${subcmd}" in
                list) [[ ${cur} == -* ]] && COMPREPLY=( $(compgen -W "--type --json" -- "${cur}") ) ;;
                save) [[ ${cur} == -* ]] && COMPREPLY=( $(compgen -W "--name --type --description --content --json" -- "${cur}") ) ;;
                search) [[ ${cur} == -* ]] && COMPREPLY=( $(compgen -W "--limit --json" -- "${cur}") ) ;;
                delete) [[ ${cur} == -* ]] && COMPREPLY=( $(compgen -W "--json" -- "${cur}") ) ;;
            esac
            return 0
            ;;

        config)
            if [[ ${COMP_CWORD} -eq 2 ]]; then
                COMPREPLY=( $(compgen -W "list get set toggle" -- "${cur}") )
                return 0
            fi
            [[ ${cur} == -* ]] && COMPREPLY=( $(compgen -W "--json" -- "${cur}") )
            return 0
            ;;

        profile)
            if [[ ${COMP_CWORD} -eq 2 ]]; then
                COMPREPLY=( $(compgen -W "list apply" -- "${cur}") )
                return 0
            fi
            [[ ${cur} == -* ]] && COMPREPLY=( $(compgen -W "--json" -- "${cur}") )
            return 0
            ;;

        trust)
            if [[ ${COMP_CWORD} -eq 2 ]]; then
                COMPREPLY=( $(compgen -W "status trust untrust" -- "${cur}") )
                return 0
            fi
            [[ ${cur} == -* ]] && COMPREPLY=( $(compgen -W "--path --json" -- "${cur}") )
            return 0
            ;;

        provider)
            if [[ ${COMP_CWORD} -eq 2 ]]; then
                COMPREPLY=( $(compgen -W "list info switch" -- "${cur}") )
                return 0
            fi
            [[ ${cur} == -* ]] && COMPREPLY=( $(compgen -W "--config --json" -- "${cur}") )
            return 0
            ;;

        doctor|status|policy|tools|mcp)
            [[ ${cur} == -* ]] && COMPREPLY=( $(compgen -W "--config --json" -- "${cur}") )
            return 0
            ;;

        cost)
            if [[ ${COMP_CWORD} -eq 2 ]]; then
                COMPREPLY=( $(compgen -W "summary economy savings" -- "${cur}") )
                return 0
            fi
            case "${subcmd}" in
                economy)
                    if [[ ${COMP_CWORD} -eq 3 ]]; then
                        COMPREPLY=( $(compgen -W "frugal balanced quality" -- "${cur}") )
                        return 0
                    fi
                    ;;
            esac
            [[ ${cur} == -* ]] && COMPREPLY=( $(compgen -W "--config --json" -- "${cur}") )
            return 0
            ;;

        search)
            if [[ ${COMP_CWORD} -eq 2 ]]; then
                COMPREPLY=( $(compgen -W "index stats" -- "${cur}") )
                return 0
            fi
            case "${prev}" in
                --mode) COMPREPLY=( $(compgen -W "semantic hybrid" -- "${cur}") ); return 0 ;;
            esac
            [[ ${cur} == -* ]] && COMPREPLY=( $(compgen -W "--mode --limit --json" -- "${cur}") )
            return 0
            ;;

        review)
            [[ ${cur} == -* ]] && COMPREPLY=( $(compgen -W "--output-format --config" -- "${cur}") )
            return 0
            ;;

        commit)
            [[ ${cur} == -* ]] && COMPREPLY=( $(compgen -W "--output-format --config" -- "${cur}") )
            return 0
            ;;
    esac
}

complete -F _poor_cli_complete poor-cli
complete -F _poor_cli_complete poor-cli-sync

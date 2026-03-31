#compdef poor-cli poor-cli-sync

# Zsh completion for poor-cli
# Add to ~/.zshrc:
#   fpath=(/path/to/completions $fpath)
#   autoload -Uz compinit && compinit

_poor_cli() {
    local -a root_commands task_subcommands automation_subcommands agent_subcommands mini_subcommands
    root_commands=(
        'help:Show root help'
        'version:Print version'
        'tui:Launch Rust TUI'
        'install:Run installer wizard'
        'install-info:Inspect launcher selection'
        'exec:Run one shared-core request'
        'task:Manage durable tasks'
        'automation:Manage scheduled automations'
        'github-task:Create task from GitHub event'
        'skills:List and run skills'
        'commands:List and run command wrappers'
        'server:Run JSON-RPC server'
        'telegram:Run Telegram bot frontend'
        'watch:Watch files for inline instructions'
        'deploy:Deploy project'
        'preview:Run preview server'
        'review-pr:Review GitHub PR'
        'agent:Manage background agents'
    )
    task_subcommands=(
        'create:Create a task'
        'list:List tasks'
        'show:Show task details'
        'start:Start queued task'
        'wait:Wait for completion'
        'approve:Approve task'
        'cancel:Cancel task'
        'retry:Retry task'
        'replay:Replay task'
        'run:Run worker (internal)'
    )
    automation_subcommands=(
        'create:Create automation'
        'list:List automations'
        'show:Show automation'
        'enable:Enable automation'
        'disable:Disable automation'
        'run-now:Run automation now'
        'run-due:Run due automations'
        'serve:Run automation scheduler loop'
        'history:Show automation history'
        'replay:Replay last automation run'
    )
    agent_subcommands=(
        'start:Start background agent'
        'list:List agents'
        'logs:Show agent logs'
        'result:Show agent result'
        'cancel:Cancel agent'
        'run:Run agent worker (internal)'
    )
    mini_subcommands=(
        'list:List entries'
        'show:Show entry details'
        'run:Run entry'
    )

    if (( CURRENT == 2 )); then
        _describe -t commands 'poor-cli commands' root_commands
        return
    fi

    local cmd=$words[2]
    case "$cmd" in
        exec)
            _arguments \
                '--prompt=[Prompt to send]' \
                '--output-format=[Output mode]:format:(text json stream-json)' \
                '--resume[Prefix prompt with recent session history]' \
                '--allow-tool=[Allow named tool]' \
                '--deny-tool=[Deny named tool]' \
                '--plan-only[Return plan without executing tools]' \
                '--provider=[Override provider]' \
                '--model=[Override model]' \
                '--routing-mode=[Routing policy]:mode:(manual quality speed cheap private)' \
                '--api-key=[Override API key]' \
                '--config=[Path to config file]:file:_files' \
                '--cwd=[Working directory]:directory:_files -/' \
                '--sandbox-preset=[Capability preset]:preset:(read-only review-only workspace-write full-access)' \
                '--permission-mode=[Permission mode]:mode:(prompt auto-safe danger-full-access)' \
                '--auto-approve[Auto-approve guarded operations]' \
                '--context-file=[Attach context file]:file:_files' \
                '--pinned-context-file=[Attach pinned context file]:file:_files' \
                '--context-budget-tokens=[Context token budget]'
            ;;

        task)
            if (( CURRENT == 3 )); then
                _describe -t task_subcommands 'task commands' task_subcommands
                return
            fi
            case "$words[3]" in
                create)
                    _arguments \
                        '--title=[Task title]' \
                        '--prompt=[Task prompt]' \
                        '--preset=[Sandbox preset]:preset:(read-only review-only workspace-write full-access)' \
                        '--source=[Task source]' \
                        '--requires-approval[Require manual approval]' \
                        '--auto-approve[Approve immediately]' \
                        '--approve[Alias for --auto-approve]' \
                        '--auto-start[Start after creation]' \
                        '--no-auto-start[Do not start after creation]' \
                        '--provider=[Provider override]' \
                        '--model=[Model override]' \
                        '--routing-mode=[Routing policy]:mode:(manual quality speed cheap private)' \
                        '--timezone=[IANA timezone]' \
                        '--execution-mode=[Execution mode]:mode:(worktree local)' \
                        '--reasoning-effort=[Reasoning effort]:effort:(low medium high)' \
                        '--config=[Path to config file]:file:_files' \
                        '--context-file=[Attach context file]:file:_files' \
                        '--pinned-context-file=[Attach pinned context file]:file:_files' \
                        '--context-budget-tokens=[Context token budget]' \
                        '--wait[Wait for completion]' \
                        '--wait-timeout-seconds=[Wait timeout seconds]' \
                        '--json[Emit JSON payload]'
                    ;;
                list)
                    _arguments '--status=[Filter by status]' '--inbox[Only inbox tasks]' '--json[Emit JSON payload]'
                    ;;
                show)
                    _arguments '1:task id:' '--response[Include response]' '--events[Include events]' '--log[Include logs]' '--json[Emit JSON payload]'
                    ;;
                start)
                    _arguments '1:task id:' '--wait[Wait for completion]' '--wait-timeout-seconds=[Wait timeout seconds]' '--json[Emit JSON payload]'
                    ;;
                wait)
                    _arguments '1:task id:' '--timeout-seconds=[Wait timeout seconds]' '--json[Emit JSON payload]'
                    ;;
                approve|retry|replay)
                    _arguments '1:task id:' '--no-auto-start[Do not start immediately]' '--wait[Wait for completion]' '--wait-timeout-seconds=[Wait timeout seconds]' '--json[Emit JSON payload]'
                    ;;
                cancel)
                    _arguments '1:task id:' '--json[Emit JSON payload]'
                    ;;
                run)
                    _arguments '--task-id=[Task id]' '--repo-root=[Repository root]:directory:_files -/' '--config=[Path to config file]:file:_files'
                    ;;
            esac
            ;;

        automation)
            if (( CURRENT == 3 )); then
                _describe -t automation_subcommands 'automation commands' automation_subcommands
                return
            fi
            case "$words[3]" in
                create)
                    _arguments \
                        '--name=[Automation name]' \
                        '--prompt=[Automation prompt]' \
                        '--every-minutes=[Run every N minutes]' \
                        '--daily=[Daily schedule HH:MM]' \
                        '--weekly=[Weekly schedule mon,wed@HH:MM]' \
                        '--preset=[Sandbox preset]:preset:(read-only review-only workspace-write full-access)' \
                        '--requires-approval[Require manual approval]' \
                        '--auto-approve[Auto-approve runs]' \
                        '--disabled[Create in disabled state]' \
                        '--provider=[Provider override]' \
                        '--model=[Model override]' \
                        '--routing-mode=[Routing policy]:mode:(manual quality speed cheap private)' \
                        '--timezone=[IANA timezone]' \
                        '--execution-mode=[Execution mode]:mode:(worktree local)' \
                        '--reasoning-effort=[Reasoning effort]:effort:(low medium high)' \
                        '--config=[Path to config file]:file:_files' \
                        '--context-file=[Attach context file]:file:_files' \
                        '--pinned-context-file=[Attach pinned context file]:file:_files' \
                        '--context-budget-tokens=[Context token budget]' \
                        '--run-now[Queue immediate run]' \
                        '--wait[Wait for completion]' \
                        '--wait-timeout-seconds=[Wait timeout seconds]' \
                        '--json[Emit JSON payload]'
                    ;;
                list)
                    _arguments '--enabled[Only enabled automations]' '--disabled[Only disabled automations]' '--json[Emit JSON payload]'
                    ;;
                show|enable|disable)
                    _arguments '1:automation id:' '--json[Emit JSON payload]'
                    ;;
                run-now|replay)
                    _arguments '1:automation id:' '--wait[Wait for completion]' '--wait-timeout-seconds=[Wait timeout seconds]' '--json[Emit JSON payload]'
                    ;;
                run-due)
                    _arguments '--limit=[Max due runs to process]' '--wait[Wait for completion]' '--wait-timeout-seconds=[Wait timeout seconds]' '--json[Emit JSON payload]'
                    ;;
                serve)
                    _arguments '--poll-seconds=[Polling interval seconds]'
                    ;;
                history)
                    _arguments '1:automation id:' '--limit=[History entry limit]' '--json[Emit JSON payload]'
                    ;;
            esac
            ;;

        agent)
            if (( CURRENT == 3 )); then
                _describe -t agent_subcommands 'agent commands' agent_subcommands
                return
            fi
            case "$words[3]" in
                start)
                    _arguments '--prompt=[Task prompt]' '-p[Task prompt]' '--sandbox=[Sandbox preset]' '--no-worktree[Run in current directory]' '--max-runtime=[Max runtime in seconds]' '--max-cost=[Max cost in USD]' '--json[Emit JSON payload]'
                    ;;
                list)
                    _arguments '--status=[Filter by status]' '--json[Emit JSON payload]'
                    ;;
                logs)
                    _arguments '1:agent id:' '--tail=[Tail line count]'
                    ;;
                result|cancel)
                    _arguments '1:agent id:'
                    ;;
                run)
                    _arguments '--agent-id=[Agent id]' '--repo-root=[Repository root]:directory:_files -/'
                    ;;
            esac
            ;;

        skills)
            if (( CURRENT == 3 )); then
                _describe -t skills_subcommands 'skills commands' mini_subcommands
                return
            fi
            if [[ "$words[3]" == 'list' ]]; then
                _arguments '--json[Emit JSON payload]'
            elif [[ "$words[3]" == 'show' ]]; then
                _arguments '1:skill name:'
            elif [[ "$words[3]" == 'run' ]]; then
                _arguments '1:skill name:' '*:request words:'
            fi
            ;;

        commands)
            if (( CURRENT == 3 )); then
                _describe -t wrapper_subcommands 'commands commands' mini_subcommands
                return
            fi
            if [[ "$words[3]" == 'list' ]]; then
                _arguments '--json[Emit JSON payload]'
            elif [[ "$words[3]" == 'show' ]]; then
                _arguments '1:command name:'
            elif [[ "$words[3]" == 'run' ]]; then
                _arguments '1:command name:' '*:args text:'
            fi
            ;;

        github-task)
            if (( CURRENT == 3 )); then
                _describe -t github_subcommands 'github-task commands' 'create:Create task from event payload'
                return
            fi
            _arguments \
                '--event-path=[Path to event payload JSON]:file:_files' \
                '--mode=[Task mode]:mode:(read-only review-only)' \
                '--auto-start[Auto start generated task]' \
                '--no-auto-start[Do not auto start]' \
                '--provider=[Provider override]' \
                '--model=[Model override]' \
                '--config=[Path to config file]:file:_files' \
                '--context-file=[Attach context file]:file:_files' \
                '--pinned-context-file=[Attach pinned context file]:file:_files' \
                '--context-budget-tokens=[Context token budget]' \
                '--wait[Wait for completion]' \
                '--wait-timeout-seconds=[Wait timeout seconds]' \
                '--json[Emit JSON payload]'
            ;;

        server)
            _arguments \
                '--stdio[Use stdio transport]' \
                '--host[Run multiplayer signaling host mode]' \
                '--bind=[Host bind address]' \
                '--port=[Host port]' \
                '--room=[Room name]' \
                '--permission-mode=[Default permission mode]:mode:(prompt auto-safe danger-full-access)' \
                '--ngrok[Launch ngrok helper]' \
                '--bridge[Run stdio to P2P bridge mode]' \
                '--invite=[Invite code]' \
                '--verbose[Enable verbose logging]'
            ;;

        telegram)
            if (( CURRENT == 3 )); then
                _describe -t telegram_subcommands 'telegram shortcuts' 'setup:Show setup guide'
            fi
            _arguments \
                '--token=[Telegram bot token]' \
                '--allowed-users=[Comma-separated Telegram user IDs]' \
                '--sandbox-preset=[Capability sandbox preset]' \
                '--max-sessions=[Maximum concurrent sessions]' \
                '--edit-interval=[Message edit interval seconds]' \
                '--webhook-url=[Webhook URL]' \
                '--webhook-port=[Webhook port]' \
                '(-v --verbose)'{-v,--verbose}'[Enable INFO-level logs]' \
                '--debug[Enable DEBUG-level logs]' \
                '--log-file=[Log file path]:file:_files'
            ;;

        watch)
            _arguments '--debounce=[Debounce seconds]' '--scan[Scan once and exit]'
            ;;

        deploy)
            _arguments '--target=[Deploy target]:target:(vercel netlify fly railway cloudflare)' '-t[Deploy target]:target:(vercel netlify fly railway cloudflare)' '--prod[Deploy to production]' '--list[List detected targets]' '--json[Emit JSON payload]'
            ;;

        preview)
            _arguments '--port=[Preview port]' '--stop[Stop preview server]'
            ;;

        review-pr)
            _arguments '1:PR number:' '--post[Post review as PR comment]' '--json[Emit JSON payload]' '--ci[Return non-zero if checks fail]'
            ;;
    esac
}

_poor_cli "$@"

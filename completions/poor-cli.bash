# Bash completion for poor-cli
# Source this file or add to ~/.bashrc:
#   source /path/to/poor-cli.bash

_poor_cli_complete() {
    local cur prev opts
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"

    # Available commands
    opts="/help /quit /exit /clear /history /sessions /new-session /checkpoints /checkpoint /rewind /diff /provider /switch /config /verbose /plan-mode /watch /unwatch /qa /api-key /multiplayer /kick /bang"

    # Provider names
    local providers="gemini openai anthropic ollama"

    # Model names
    local models="gemini-2.0-flash gemini-1.5-pro gpt-4o gpt-4o-mini gpt-4-turbo claude-3-5-sonnet claude-3-opus llama3 mistral codellama"

    # Complete commands starting with /
    if [[ ${cur} == /* ]] ; then
        COMPREPLY=( $(compgen -W "${opts}" -- ${cur}) )
        return 0
    fi

    # Complete file paths after certain commands
    case "${prev}" in
        /diff|/rewind|/watch)
            COMPREPLY=( $(compgen -f -- ${cur}) )
            return 0
            ;;
        /provider|/switch)
            COMPREPLY=( $(compgen -W "${providers}" -- ${cur}) )
            return 0
            ;;
        /api-key)
            COMPREPLY=( $(compgen -W "set get delete list ${providers}" -- ${cur}) )
            return 0
            ;;
        --provider)
            COMPREPLY=( $(compgen -W "${providers}" -- ${cur}) )
            return 0
            ;;
        --model)
            COMPREPLY=( $(compgen -W "${models}" -- ${cur}) )
            return 0
            ;;
    esac
}

complete -F _poor_cli_complete poor-cli
complete -F _poor_cli_complete poor-cli-sync

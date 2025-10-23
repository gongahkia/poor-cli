# Bash completion for poor-cli
# Source this file or add to ~/.bashrc:
#   source /path/to/poor-cli.bash

_poor_cli_complete() {
    local cur prev opts
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"

    # Available commands
    opts="/help /quit /exit /clear /history /sessions /new-session /checkpoints /checkpoint /rewind /diff /provider /switch /config /verbose /plan-mode"

    # Complete commands starting with /
    if [[ ${cur} == /* ]] ; then
        COMPREPLY=( $(compgen -W "${opts}" -- ${cur}) )
        return 0
    fi

    # Complete file paths after certain commands
    case "${prev}" in
        /diff|/rewind)
            COMPREPLY=( $(compgen -f -- ${cur}) )
            return 0
            ;;
    esac
}

complete -F _poor_cli_complete poor-cli
complete -F _poor_cli_complete poor-cli-sync

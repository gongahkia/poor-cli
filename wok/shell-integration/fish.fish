# Wok terminal shell integration for Fish
# Emits OSC 133 markers for block detection

function __wok_prompt --on-event fish_prompt
    printf '\033]133;D;%d\007' $status
    printf '\033]133;A\007'
    printf '\033]7;file://%s%s\007' (hostname) (pwd)
end

function __wok_preexec --on-event fish_preexec
    printf '\033]133;E;%s\007' "$argv[1]"
    printf '\033]133;B\007'
    printf '\033]133;C\007'
end

printf '\033]133;A\007'

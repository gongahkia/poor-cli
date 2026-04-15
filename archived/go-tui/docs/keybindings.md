# Keybindings

`gocli-poor` keybindings are configured in YAML under `keybindings`.

## Defaults

| Action | Default | Effect |
|---|---|---|
| `submit` | `ctrl+enter` | Send input. |
| `cancel` | `ctrl+c,esc` | Cancel or close active input/modal. |
| `palette` | `/` | Open slash-command palette from empty input. |
| `mention` | `@` | Open mention picker. |
| `focus.chat` | `ctrl+j` | Focus chat transcript. |
| `focus.input` | `ctrl+i` | Focus prompt input. |
| `scroll.up` | `pgup` | Scroll chat up one viewport. |
| `scroll.down` | `pgdn` | Scroll chat down one viewport. |
| `scroll.top` | `home` | Jump chat to top. |
| `scroll.bottom` | `end` | Jump chat to bottom. |
| `accept.edit` | `ctrl+y` | Accept current edit review item. |
| `reject.edit` | `ctrl+n` | Reject current edit review item. |
| `regen.edit` | `ctrl+r` | Regenerate current edit review item. |
| `quit` | `ctrl+q` | Quit the TUI. |

## Rebind

Config file:

```yaml
keybindings:
  submit: enter
  palette: ctrl+p
  focus.chat: ctrl+x j
  cancel: ctrl+c,esc
```

Env var override:

```sh
export GOCLI_POOR_KEYBINDINGS_SUBMIT=enter
export GOCLI_POOR_KEYBINDINGS_PALETTE=ctrl+p
export GOCLI_POOR_KEYBINDINGS_FOCUS_CHAT='ctrl+x j'
```

Rules:

- Separate alternatives with commas: `ctrl+c,esc`.
- Separate chord steps with spaces: `ctrl+x p`.
- Key names are lowercase.
- `escape` normalizes to `esc`.
- `return` normalizes to `enter`.
- `pagedown` normalizes to `pgdown`; `pageup` normalizes to `pgup`.
- `ctrl+i` normalizes to `tab`.

## Accepted Keys

Single printable runes are valid: `/`, `@`, `a`, `?`, etc.

Named keys:

```txt
enter ctrl+enter esc tab shift+tab backspace delete insert
home end pgup pgdown up down left right
ctrl+home ctrl+end ctrl+pgup ctrl+pgdown ctrl+up ctrl+down ctrl+left ctrl+right
shift+home shift+end shift+up shift+down shift+left shift+right
ctrl+shift+home ctrl+shift+end ctrl+shift+up ctrl+shift+down ctrl+shift+left ctrl+shift+right
f1 through f24
alt+<any-valid-key>
ctrl+a through ctrl+z
ctrl+@ ctrl+\ ctrl+] ctrl+^ ctrl+_ ctrl+?
```

## Modal Keys

These are fixed flow controls.

| Surface | Key | Effect |
|---|---|---|
| Any modal | `esc` | Close modal. |
| Any modal | `ctrl+c`, `ctrl+q` | Quit. |
| Palette | `up`, `ctrl+p` | Previous command. |
| Palette | `down`, `ctrl+n` | Next command. |
| Palette | `enter` | Run selected command. |
| Palette | `backspace` | Delete filter char. |
| Mention picker | `up`, `ctrl+p` | Previous file. |
| Mention picker | `down`, `ctrl+n` | Next file. |
| Mention picker | `enter` | Insert selected file mention. |
| Mention picker | `esc` | Close picker. |
| Provider picker | `up`, `ctrl+p` | Previous provider. |
| Provider picker | `down`, `ctrl+n` | Next provider. |
| Provider picker | `left`, `right` | Cycle model. |
| Provider picker | `enter` | Select provider/model. |
| Session picker | `up`, `ctrl+p` | Previous session. |
| Session picker | `down`, `ctrl+n` | Next session. |
| Session picker | `enter` | Select session. |
| API-key prompt | `enter` | Submit key. |
| API-key prompt | `tab`, `space` | Toggle persistence. |
| API-key prompt | `backspace` | Delete char. |
| Permission prompt | `a` | Allow once. |
| Permission prompt | `s` | Allow for session. |
| Permission prompt | `p` | Allow permanently. |
| Permission prompt | `d`, `esc` | Deny once. |
| Diff review | `y` | Accept hunk. |
| Diff review | `n` | Reject hunk. |
| Diff review | `r` | Regenerate hunk. |
| Diff review | `Y` | Accept all. |
| Diff review | `N` | Reject all. |
| Diff review | `up`, `k` | Previous hunk. |
| Diff review | `down`, `j` | Next hunk. |
| Diff review | `left`, `h` | Previous edit. |
| Diff review | `right`, `l` | Next edit. |
| Diff review | `pgup`, `pgdown` | Scroll diff. |
| Diff review | `home`, `end` | Jump diff. |

## Input Editing

| Key | Effect |
|---|---|
| `enter` | Insert newline unless rebound as submit. |
| `backspace`, `ctrl+h` | Delete previous char. |
| `delete` | Delete next char. |
| `left`, `right` | Move cursor. |
| `home`, `end` | Move to input start/end. |
| `up`, `down` | Navigate prompt history when available. |

## Chat Focus

| Key | Effect |
|---|---|
| `pgup`, `ctrl+u` | Scroll up one viewport. |
| `pgdown`, `ctrl+d` | Scroll down one viewport. |
| `home`, `end` | Jump top/bottom. |
| `up`, `k` | Scroll one line up. |
| `down`, `j` | Scroll one line down. |
| `enter`, `space` | Toggle focused tool block. |

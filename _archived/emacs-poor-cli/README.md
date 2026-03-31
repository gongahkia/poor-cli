# emacs-poor-cli

First-party vanilla Emacs client for `poor-cli`, built on the shared stdio JSON-RPC server.

## Requirements

- Emacs 29+
- `poor-cli-server` available on `PATH`
- GNU ELPA packages `markdown-mode` and `transient`
- At least one configured provider or local Ollama setup

## Installation

### `package-vc` (vanilla Emacs 29+)

```elisp
(require 'package)
(package-initialize)
(package-vc-install
 '(poor-cli
   :url "https://github.com/gongahkia/poor-cli"
   :lisp-dir "emacs-poor-cli"))
```

### Manual clone

```elisp
(add-to-list 'load-path "/path/to/poor-cli/emacs-poor-cli")
(require 'poor-cli)
```

## Basic setup

```elisp
(require 'poor-cli)

(setq poor-cli-server-command '("poor-cli-server" "--stdio"))
(setq poor-cli-auto-start t)
(setq poor-cli-request-timeout 15)

(global-poor-cli-mode 1)
```

## Main commands

- `M-x poor-cli-dispatch`
- `M-x poor-cli-chat-open`
- `M-x poor-cli-chat-send`
- `M-x poor-cli-inline-trigger`
- `M-x poor-cli-status`
- `M-x poor-cli-trust`
- `M-x poor-cli-doctor`
- `M-x poor-cli-open-runs`
- `M-x poor-cli-open-tasks`
- `M-x poor-cli-open-automations`
- `M-x poor-cli-collab-dispatch`

## Collaboration

- `M-x poor-cli-collab-start` starts a local host.
- `M-x poor-cli-collab-join` restarts the local client in bridge mode with a signed invite.
- `M-x poor-cli-collab-summary`, `poor-cli-collab-members`, `poor-cli-collab-open-agenda`, and `poor-cli-collab-open-activity` expose the shared collaboration surfaces.

## Notes

- This package targets vanilla Emacs. Doom Emacs and Spacemacs can layer on top later.
- The Emacs client reuses the backend RPC contract used by the TUI and Neovim clients; it does not introduce a separate backend path.

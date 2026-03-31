;;; poor-cli-state.el --- Shared state and customization for poor-cli -*- lexical-binding: t; -*-

;; Package-Requires: ((emacs "29.1") (markdown-mode "2.6") (transient "0.4.0"))

;;; Commentary:

;; Shared customization, state, and hooks for the poor-cli Emacs client.

;;; Code:

(require 'cl-lib)

(defgroup poor-cli nil
  "First-party Emacs client for poor-cli."
  :group 'tools
  :prefix "poor-cli-")

(defcustom poor-cli-server-command '("poor-cli-server" "--stdio")
  "Command list used to start the poor-cli JSON-RPC server."
  :type '(repeat string)
  :group 'poor-cli)

(defcustom poor-cli-auto-start t
  "Start the poor-cli server automatically when the mode is enabled."
  :type 'boolean
  :group 'poor-cli)

(defcustom poor-cli-auto-restart t
  "Restart the poor-cli server automatically after an unexpected shutdown."
  :type 'boolean
  :group 'poor-cli)

(defcustom poor-cli-request-timeout 15
  "Default poor-cli request timeout in seconds."
  :type 'integer
  :group 'poor-cli)

(defcustom poor-cli-provider nil
  "Default provider passed to the poor-cli server during initialization."
  :type '(choice (const :tag "Auto-detect" nil) string)
  :group 'poor-cli)

(defcustom poor-cli-model nil
  "Default model passed to the poor-cli server during initialization."
  :type '(choice (const :tag "Auto-detect" nil) string)
  :group 'poor-cli)

(defcustom poor-cli-completion-provider nil
  "Optional provider override used for inline completion requests."
  :type '(choice (const :tag "Use session provider" nil) string)
  :group 'poor-cli)

(defcustom poor-cli-completion-model nil
  "Optional model override used for inline completion requests."
  :type '(choice (const :tag "Use session model" nil) string)
  :group 'poor-cli)

(defcustom poor-cli-completion-enabled t
  "Whether inline completion is enabled."
  :type 'boolean
  :group 'poor-cli)

(defcustom poor-cli-completion-manual-only nil
  "When non-nil, poor-cli inline completion only runs on explicit trigger."
  :type 'boolean
  :group 'poor-cli)

(defcustom poor-cli-completion-idle-delay 0.5
  "Idle delay in seconds before auto-triggering inline completion."
  :type 'number
  :group 'poor-cli)

(defcustom poor-cli-completion-max-chars 16000
  "Maximum characters sent when shaping an inline completion request."
  :type 'integer
  :group 'poor-cli)

(defcustom poor-cli-completion-context-lines-before 80
  "Maximum lines before point included in inline completion context."
  :type 'integer
  :group 'poor-cli)

(defcustom poor-cli-completion-context-lines-after 80
  "Maximum lines after point included in inline completion context."
  :type 'integer
  :group 'poor-cli)

(defcustom poor-cli-completion-filetype-allowlist nil
  "Optional allowlist of file extensions eligible for inline completion."
  :type '(repeat string)
  :group 'poor-cli)

(defcustom poor-cli-completion-filetype-blocklist nil
  "File extensions blocked from inline completion."
  :type '(repeat string)
  :group 'poor-cli)

(defcustom poor-cli-completion-major-mode-blocklist
  '(special-mode dired-mode shell-mode eshell-mode term-mode vterm-mode)
  "Major modes blocked from inline completion."
  :type '(repeat symbol)
  :group 'poor-cli)

(defcustom poor-cli-chat-display-action
  '((display-buffer-reuse-window display-buffer-below-selected))
  "Display action used for chat, review, and markdown scratch buffers."
  :type 'sexp
  :group 'poor-cli)

(defcustom poor-cli-multiplayer-invite nil
  "Optional signed collaboration invite used when bootstrapping bridge mode."
  :type '(choice (const :tag "Disabled" nil) string)
  :group 'poor-cli)

(defcustom poor-cli-debug nil
  "Enable verbose debug logging in the Emacs client."
  :type 'boolean
  :group 'poor-cli)

(defconst poor-cli-chat-buffer-name "*poor-cli-chat*")
(defconst poor-cli-runs-buffer-name "*poor-cli-runs*")
(defconst poor-cli-tasks-buffer-name "*poor-cli-tasks*")
(defconst poor-cli-automations-buffer-name "*poor-cli-automations*")
(defconst poor-cli-members-buffer-name "*poor-cli-members*")
(defconst poor-cli-agenda-buffer-name "*poor-cli-agenda*")
(defconst poor-cli-activity-buffer-name "*poor-cli-activity*")
(defconst poor-cli-review-buffer-name "*poor-cli-review*")
(defconst poor-cli-checkpoints-buffer-name "*poor-cli-checkpoints*")
(defconst poor-cli-memory-buffer-name "*poor-cli-memory*")
(defconst poor-cli-sessions-buffer-name "*poor-cli-sessions*")
(defconst poor-cli-agents-buffer-name "*poor-cli-agents*")
(defconst poor-cli-config-buffer-name "*poor-cli-config*")
(defconst poor-cli-history-buffer-name "*poor-cli-history*")
(defconst poor-cli-custom-commands-buffer-name "*poor-cli-custom-commands*")
(defconst poor-cli-skills-buffer-name "*poor-cli-skills*")
(defconst poor-cli-profiles-buffer-name "*poor-cli-profiles*")
(defconst poor-cli-providers-buffer-name "*poor-cli-providers*")
(defconst poor-cli-log-buffer-name "*poor-cli-server-stderr*")

(defvar poor-cli--status-state 'stopped)
(defvar poor-cli--status-message "Stopped")
(defvar poor-cli--capabilities nil)
(defvar poor-cli--last-error nil)
(defvar poor-cli--last-request nil)
(defvar poor-cli--stderr-buffer nil)
(defvar poor-cli--manual-stop nil)
(defvar poor-cli--current-inline-request-id nil)
(defvar poor-cli--current-chat-request-id nil)

(defun poor-cli--default-multiplayer-state ()
  "Return the default multiplayer state plist."
  (list :enabled nil
        :room ""
        :role ""
        :uiRole ""
        :displayName ""
        :approvalState ""
        :handRaised nil
        :queuePosition 0
        :connectionId ""
        :memberCount 0
        :queueDepth 0
        :activeConnectionId ""
        :lobbyEnabled nil
        :preset ""
        :lastEventType ""
        :members nil
        :lastSuggestion nil))

(defvar poor-cli--multiplayer-state (poor-cli--default-multiplayer-state))

(defvar poor-cli-status-changed-hook nil
  "Hook run when the poor-cli connection status changes.")

(defvar poor-cli-thinking-chunk-hook nil
  "Hook run for thinking chunk notifications.")

(defvar poor-cli-stream-chunk-hook nil
  "Hook run for stream chunk notifications.")

(defvar poor-cli-inline-chunk-hook nil
  "Hook run for inline completion chunk notifications.")

(defvar poor-cli-tool-event-hook nil
  "Hook run for tool event notifications.")

(defvar poor-cli-progress-hook nil
  "Hook run for progress notifications.")

(defvar poor-cli-cost-update-hook nil
  "Hook run for cost update notifications.")

(defvar poor-cli-permission-request-hook nil
  "Hook run for permission review notifications.")

(defvar poor-cli-plan-request-hook nil
  "Hook run for plan review notifications.")

(defvar poor-cli-room-event-hook nil
  "Hook run for collaboration room event notifications.")

(defvar poor-cli-member-role-updated-hook nil
  "Hook run for collaboration member role update notifications.")

(defvar poor-cli-suggestion-hook nil
  "Hook run for collaboration suggestion notifications.")

(defun poor-cli-reset-session-state ()
  "Reset client-side session state."
  (setq poor-cli--status-state 'stopped
        poor-cli--status-message "Stopped"
        poor-cli--capabilities nil
        poor-cli--last-error nil
        poor-cli--last-request nil
        poor-cli--current-inline-request-id nil
        poor-cli--current-chat-request-id nil
        poor-cli--multiplayer-state (poor-cli--default-multiplayer-state)))

(defun poor-cli-set-status (state message)
  "Update the client STATE and status MESSAGE."
  (setq poor-cli--status-state state
        poor-cli--status-message message)
  (run-hooks 'poor-cli-status-changed-hook))

(defun poor-cli-client-status ()
  "Return a plist describing the current Emacs client status."
  (list :state poor-cli--status-state
        :message poor-cli--status-message
        :capabilities poor-cli--capabilities
        :last-error poor-cli--last-error
        :last-request poor-cli--last-request
        :stderr-buffer poor-cli--stderr-buffer
        :multiplayer poor-cli--multiplayer-state))

(provide 'poor-cli-state)

;;; poor-cli-state.el ends here

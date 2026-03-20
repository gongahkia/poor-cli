;;; poor-cli-commands.el --- Interactive commands for poor-cli -*- lexical-binding: t; -*-

;;; Code:

(require 'subr-x)
(require 'markdown-mode)
(require 'transient)
(require 'poor-cli-rpc)
(require 'poor-cli-chat)
(require 'poor-cli-collab)
(require 'poor-cli-inline)
(require 'poor-cli-lists)

(defun poor-cli-commands--open-markdown (name content)
  "Open markdown scratch buffer NAME with CONTENT."
  (let ((buffer (get-buffer-create name)))
    (with-current-buffer buffer
      (markdown-mode)
      (let ((inhibit-read-only t))
        (erase-buffer)
        (insert content)
        (goto-char (point-min))
        (read-only-mode 1)))
    (display-buffer buffer poor-cli-chat-display-action)))

(defun poor-cli-commands--format-status (payload)
  "Format status PAYLOAD as markdown."
  (let* ((session (plist-get payload :session))
         (provider (plist-get payload :provider))
         (active (plist-get provider :active))
         (context (plist-get payload :context))
         (preview (plist-get context :lastPreview))
         (collab (plist-get payload :collaboration))
         (recovery (plist-get payload :recovery))
         (mutation (plist-get recovery :lastMutation)))
    (mapconcat
     #'identity
     (list "# poor-cli status"
           ""
           (format "- Provider: `%s`" (or (plist-get active :name) "unknown"))
           (format "- Model: `%s`" (or (plist-get active :model) "unknown"))
           (format "- Routing mode: `%s`" (or (plist-get session :routingMode) "manual"))
           (format "- Permission mode: `%s`" (or (plist-get session :permissionMode) "prompt"))
           (format "- Context selected: %s" (length (poor-cli--normalize-seq (plist-get preview :selected))))
           (format "- Context excluded: %s" (length (poor-cli--normalize-seq (plist-get preview :excluded))))
           (format "- Context tokens: %s" (or (plist-get preview :totalTokens) 0))
           (format "- Collaboration role: `%s`" (or (plist-get collab :role) "solo"))
           (format "- Collaboration room: `%s`" (or (plist-get collab :room) ""))
           (format "- Collaboration members: %s" (or (plist-get collab :memberCount) 0))
           (format "- Last mutation: `%s`" (or (plist-get mutation :intent) "")))
     "\n")))

(defun poor-cli-commands--format-trust (payload)
  "Format trust PAYLOAD as markdown."
  (let* ((trust (plist-get payload :trust))
         (provider (plist-get payload :provider))
         (active (plist-get provider :active))
         (policy (plist-get trust :policy))
         (hooks (plist-get policy :hooks))
         (recovery (plist-get payload :recovery))
         (mutation (plist-get recovery :lastMutation)))
    (mapconcat
     #'identity
     (list "# poor-cli trust"
           ""
           (format "- Provider: `%s/%s`"
                   (or (plist-get active :name) "unknown")
                   (or (plist-get active :model) "unknown"))
           (format "- Routing mode: `%s`" (or (plist-get active :routingMode) "manual"))
           (format "- Sandbox preset: `%s`" (or (plist-get trust :sandboxPreset) ""))
           (format "- Privacy posture: `%s`" (or (plist-get provider :privacyPosture) "unknown"))
           (format "- Checkpointing: `%s`" (plist-get trust :checkpointing))
           (format "- Trusted workspace boundary: `%s`"
                   (plist-get (plist-get trust :security) :trustedWorkspaceBoundary))
           (format "- Policy hooks: %s" (or (plist-get hooks :totalHooks) 0))
           (format "- Hook validation errors: %s"
                   (length (poor-cli--normalize-seq (plist-get hooks :validationErrors))))
           (if-let ((last-error (plist-get provider :lastError)))
               (format "- Last provider error: %s" last-error)
             "- Last provider error: none")
           (format "- Last checkpoint: `%s`" (or (plist-get mutation :checkpointId) "")))
     "\n")))

(defun poor-cli-commands--format-doctor (payload)
  "Format doctor PAYLOAD as markdown."
  (let ((summary (plist-get payload :summary))
        (checks (poor-cli--normalize-seq (plist-get payload :checks))))
    (concat
     (mapconcat
      #'identity
      (list "# poor-cli doctor"
            ""
            (format "- Overall: `%s`" (or (plist-get summary :overall) "unknown"))
            (format "- Ready providers: %s" (or (plist-get summary :readyProviderCount) 0))
            (format "- Routing mode: `%s`" (or (plist-get summary :routingMode) "manual"))
            (format "- Privacy posture: `%s`" (or (plist-get summary :privacyPosture) "unknown"))
            "")
      "\n")
     (mapconcat
      (lambda (check)
        (mapconcat
         #'identity
         (list (format "## %s" (or (plist-get check :title) "Check"))
               (format "- Status: `%s`" (or (plist-get check :status) "unknown"))
               (format "- Message: %s" (or (plist-get check :message) ""))
               (format "- Action: %s" (or (plist-get check :action) ""))
               "")
         "\n"))
      checks
      ""))))

(defun poor-cli-commands--format-workflow (payload)
  "Format workflow PAYLOAD as markdown."
  (if-let ((workflow (plist-get payload :workflow)))
      (mapconcat
       #'identity
       (list (format "# workflow %s" (or (plist-get workflow :name) ""))
             ""
             (or (plist-get workflow :description) "")
             ""
             (format "- Sandbox: `%s`"
                     (or (plist-get workflow :defaultSandboxPreset)
                         (plist-get workflow :sandboxPreset)
                         ""))
             (format "- Context strategy: %s"
                     (or (plist-get workflow :contextStrategy)
                         (plist-get workflow :suggestedContextStrategy)
                         ""))
             ""
             "```text"
             (or (plist-get workflow :starterPrompt)
                 (plist-get workflow :promptScaffold)
                 "")
             "```")
       "\n")
    (let ((workflows (poor-cli--normalize-seq (plist-get payload :workflows)))
          (recommended (plist-get payload :recommended)))
      (concat "# workflows\n\n"
              (mapconcat
               (lambda (workflow)
                 (format "- `%s`%s: %s"
                         (or (plist-get workflow :name) "")
                         (if (equal (plist-get workflow :name) recommended) " (recommended)" "")
                         (or (plist-get workflow :description) "")))
               workflows
               "\n")))))

(defun poor-cli-commands--format-context (payload)
  "Format context explain PAYLOAD as markdown."
  (concat
   (mapconcat
    #'identity
    (list "# context explain"
          ""
          (format "- Total tokens: %s" (or (plist-get payload :totalTokens) 0))
          (format "- Budget tokens: %s" (or (plist-get payload :budgetTokens) 0))
          (format "- Truncated: `%s`" (plist-get payload :truncated))
          (format "- Message: %s" (or (plist-get payload :message) ""))
          ""
          "## Selected")
    "\n")
   "\n"
   (mapconcat
    (lambda (item)
      (format "- `%s` [%s] %s"
              (or (plist-get item :path) "")
              (or (plist-get item :source) "auto")
              (or (plist-get item :reason) "")))
    (poor-cli--normalize-seq (plist-get payload :selected))
    "\n")
   (if-let ((excluded (poor-cli--normalize-seq (plist-get payload :excluded))))
       (if excluded
           (concat "\n\n## Excluded\n"
                   (mapconcat
                    (lambda (item)
                      (format "- `%s` [%s]"
                              (or (plist-get item :path) "")
                              (or (plist-get item :excludedReason) "")))
                    excluded
                    "\n"))
         "")
     "")))

(defun poor-cli-status ()
  "Open the shared poor-cli status summary."
  (interactive)
  (poor-cli-commands--open-markdown
   "*poor-cli-status*"
   (poor-cli-commands--format-status (poor-cli-get-status-view))))

(defun poor-cli-trust ()
  "Open the poor-cli trust center."
  (interactive)
  (poor-cli-commands--open-markdown
   "*poor-cli-trust*"
   (poor-cli-commands--format-trust (poor-cli-get-trust-view))))

(defun poor-cli-doctor ()
  "Open the poor-cli doctor report."
  (interactive)
  (poor-cli-commands--open-markdown
   "*poor-cli-doctor*"
   (poor-cli-commands--format-doctor (poor-cli-get-doctor-report))))

(defun poor-cli-workflow (&optional name)
  "Open the poor-cli workflow view for NAME or the workflow list."
  (interactive
   (let* ((payload (poor-cli-list-workflows))
          (workflows (mapcar
                      (lambda (workflow) (or (plist-get workflow :name) ""))
                      (poor-cli--normalize-seq (plist-get payload :workflows))))
          (choices (cons "" workflows))
          (selected (completing-read "Workflow (empty for list): " choices nil t)))
     (list (unless (string-empty-p selected) selected))))
  (poor-cli-commands--open-markdown
   "*poor-cli-workflow*"
   (poor-cli-commands--format-workflow
    (if (and name (not (string-empty-p name)))
        (poor-cli-get-workflow name)
      (poor-cli-list-workflows)))))

(defun poor-cli-context ()
  "Open the backend context explanation for the current editing session."
  (interactive)
  (poor-cli-commands--open-markdown
   "*poor-cli-context*"
   (poor-cli-commands--format-context
    (poor-cli-get-context-explain
     (list :message "Explain the current context plan for this editing session."
           :contextFiles (when buffer-file-name (list buffer-file-name)))))))

(defun poor-cli-open-runs ()
  "Open shared run history."
  (interactive)
  (poor-cli-lists-open-runs))

(defun poor-cli-open-tasks ()
  "Open durable task list."
  (interactive)
  (poor-cli-lists-open-tasks nil))

(defun poor-cli-open-inbox ()
  "Open actionable durable tasks."
  (interactive)
  (poor-cli-lists-open-tasks t))

(defun poor-cli-open-automations ()
  "Open scheduled automations."
  (interactive)
  (poor-cli-lists-open-automations))

(defun poor-cli-switch-provider-command (provider model)
  "Interactively switch poor-cli to PROVIDER and optional MODEL."
  (interactive
   (list (completing-read "Provider: " '("gemini" "openai" "anthropic" "ollama") nil t)
         (read-string "Model (optional): ")))
  (poor-cli-switch-provider provider (unless (string-empty-p model) model))
  (message "[poor-cli] Switched provider to %s" provider))

(defun poor-cli-open-log ()
  "Open the poor-cli stderr log buffer."
  (interactive)
  (if (buffer-live-p poor-cli--stderr-buffer)
      (display-buffer poor-cli--stderr-buffer)
    (message "[poor-cli] No stderr buffer available")))

(transient-define-prefix poor-cli-dispatch ()
  "Root poor-cli command menu."
  [["Lifecycle"
    ("s" "Start" poor-cli-start)
    ("x" "Stop" poor-cli-stop)
    ("r" "Restart" poor-cli-restart)
    ("k" "Cancel request" poor-cli-chat-cancel)]
   ["Chat"
    ("c" "Chat buffer" poor-cli-chat-open)
    ("p" "Send prompt" poor-cli-chat-send)
    ("R" "Send region" poor-cli-chat-send-region)
    ("b" "Send buffer" poor-cli-chat-send-buffer)
    ("f" "Send file" poor-cli-chat-send-file)]]
  [["Inline"
    ("i" "Trigger" poor-cli-inline-trigger)
    ("a" "Accept" poor-cli-inline-accept)
    ("w" "Accept word" poor-cli-inline-accept-word)
    ("l" "Accept line" poor-cli-inline-accept-line)
    ("d" "Dismiss" poor-cli-inline-dismiss)]
   ["Inspect"
    ("S" "Status" poor-cli-status)
    ("T" "Trust" poor-cli-trust)
    ("D" "Doctor" poor-cli-doctor)
    ("W" "Workflow" poor-cli-workflow)
    ("C" "Context" poor-cli-context)]]
  [["Runs/Tasks"
    ("u" "Runs" poor-cli-open-runs)
    ("t" "Tasks" poor-cli-open-tasks)
    ("I" "Inbox" poor-cli-open-inbox)
    ("A" "Automations" poor-cli-open-automations)
    ("P" "Switch provider" poor-cli-switch-provider-command)]
   ["Collaboration"
    ("m" "Dispatch" poor-cli-collab-dispatch)
    ("M" "Summary" poor-cli-collab-summary)
    ("L" "Open log" poor-cli-open-log)
    ("q" "Clear chat" poor-cli-chat-clear)]])

(provide 'poor-cli-commands)

;;; poor-cli-commands.el ends here

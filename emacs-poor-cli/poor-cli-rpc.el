;;; poor-cli-rpc.el --- JSON-RPC process client for poor-cli -*- lexical-binding: t; -*-

;;; Commentary:

;; Process and JSON-RPC management for the poor-cli Emacs client.

;;; Code:

(require 'cl-lib)
(require 'eieio)
(require 'jsonrpc)
(require 'subr-x)
(require 'poor-cli-state)

(defvar poor-cli--connection nil)
(defvar poor-cli--restart-timer nil)

(defun poor-cli--debug (format-string &rest args)
  "Log a debug message when `poor-cli-debug' is enabled."
  (when poor-cli-debug
    (apply #'message (concat "[poor-cli] " format-string) args)))

(defun poor-cli--method (name)
  "Return a method symbol for NAME."
  (if (symbolp name) name (intern name)))

(defun poor-cli--plist (&rest pairs)
  "Return a plist from PAIRS."
  pairs)

(defun poor-cli--get-in (plist &rest keys)
  "Read nested KEYS from PLIST."
  (let ((current plist))
    (while (and keys current)
      (setq current (plist-get current (car keys))
            keys (cdr keys)))
    current))

(defun poor-cli--normalize-seq (value)
  "Normalize VALUE into a list."
  (cond
   ((null value) nil)
   ((listp value) value)
   ((vectorp value) (append value nil))
   (t (list value))))

(defun poor-cli--uuidish-id (prefix)
  "Return a unique request id using PREFIX."
  (format "%s-%d-%06d" prefix (floor (float-time)) (random 1000000)))

(defun poor-cli--server-command ()
  "Return the command list used to launch the server."
  (if (and (stringp poor-cli-multiplayer-invite)
           (not (string-empty-p poor-cli-multiplayer-invite)))
      (list "poor-cli-server" "--bridge" "--invite" poor-cli-multiplayer-invite)
    (append poor-cli-server-command nil)))

(defun poor-cli-client-capabilities ()
  "Return the client capability plist sent during initialization."
  (list :uiSurface "emacs"
        :streaming t
        :completion (list :partialStreaming t)
        :reviewFlows (list :permissionRequests t
                           :planReview t)
        :multiplayer (list :events t
                           :roleUpdates t
                           :suggestions t
                           :roomPresence t
                           :roomActions (list :suggestText t
                                              :passDriver t
                                              :listRoomMembers t))))

(defun poor-cli-running-p ()
  "Return non-nil when the poor-cli connection is running."
  (and poor-cli--connection
       (jsonrpc-running-p poor-cli--connection)))

(defun poor-cli-ready-p ()
  "Return non-nil when poor-cli has been initialized."
  (and (poor-cli-running-p)
       poor-cli--capabilities))

(defun poor-cli--capture-initialize-result (result)
  "Capture RESULT from the initialize handshake."
  (let ((caps (plist-get result :capabilities)))
    (setq poor-cli--capabilities caps)
    (when caps
      (let ((multiplayer (plist-get caps :multiplayer)))
        (when multiplayer
          (setq poor-cli--multiplayer-state
                (plist-put poor-cli--multiplayer-state :enabled (plist-get multiplayer :enabled)))
          (setq poor-cli--multiplayer-state
                (plist-put poor-cli--multiplayer-state :room (or (plist-get multiplayer :room) "")))
          (setq poor-cli--multiplayer-state
                (plist-put poor-cli--multiplayer-state :role (or (plist-get multiplayer :role) "")))
          (setq poor-cli--multiplayer-state
                (plist-put poor-cli--multiplayer-state :uiRole (or (plist-get multiplayer :uiRole) "")))
          (setq poor-cli--multiplayer-state
                (plist-put poor-cli--multiplayer-state :displayName (or (plist-get multiplayer :displayName) "")))
          (setq poor-cli--multiplayer-state
                (plist-put poor-cli--multiplayer-state :approvalState (or (plist-get multiplayer :approvalState) "")))
          (setq poor-cli--multiplayer-state
                (plist-put poor-cli--multiplayer-state :handRaised (plist-get multiplayer :handRaised)))
          (setq poor-cli--multiplayer-state
                (plist-put poor-cli--multiplayer-state :queuePosition (or (plist-get multiplayer :queuePosition) 0)))
          (setq poor-cli--multiplayer-state
                (plist-put poor-cli--multiplayer-state :connectionId (or (plist-get multiplayer :connectionId) "")))
          (setq poor-cli--multiplayer-state
                (plist-put poor-cli--multiplayer-state :lobbyEnabled (plist-get multiplayer :lobbyEnabled)))
          (setq poor-cli--multiplayer-state
                (plist-put poor-cli--multiplayer-state :preset (or (plist-get multiplayer :preset) ""))))))
    (poor-cli-set-status 'ready "Initialized")))

(defun poor-cli--apply-room-event (params)
  "Update multiplayer state from room event PARAMS."
  (setq poor-cli--multiplayer-state
        (plist-put poor-cli--multiplayer-state :enabled t))
  (setq poor-cli--multiplayer-state
        (plist-put poor-cli--multiplayer-state :room (or (plist-get params :room) "")))
  (setq poor-cli--multiplayer-state
        (plist-put poor-cli--multiplayer-state :memberCount (or (plist-get params :memberCount) 0)))
  (setq poor-cli--multiplayer-state
        (plist-put poor-cli--multiplayer-state :queueDepth (or (plist-get params :queueDepth) 0)))
  (setq poor-cli--multiplayer-state
        (plist-put poor-cli--multiplayer-state :activeConnectionId (or (plist-get params :activeConnectionId) "")))
  (setq poor-cli--multiplayer-state
        (plist-put poor-cli--multiplayer-state :lobbyEnabled (plist-get params :lobbyEnabled)))
  (setq poor-cli--multiplayer-state
        (plist-put poor-cli--multiplayer-state :preset (or (plist-get params :preset) "")))
  (setq poor-cli--multiplayer-state
        (plist-put poor-cli--multiplayer-state :lastEventType (or (plist-get params :eventType) "")))
  (setq poor-cli--multiplayer-state
        (plist-put poor-cli--multiplayer-state :members (poor-cli--normalize-seq (plist-get params :members))))
  (let ((local-id (plist-get poor-cli--multiplayer-state :connectionId)))
    (when (and (stringp local-id) (not (string-empty-p local-id)))
      (dolist (member (poor-cli--normalize-seq (plist-get poor-cli--multiplayer-state :members)))
        (when (equal local-id (plist-get member :connectionId))
          (setq poor-cli--multiplayer-state
                (plist-put poor-cli--multiplayer-state :role (or (plist-get member :role) "")))
          (setq poor-cli--multiplayer-state
                (plist-put poor-cli--multiplayer-state :uiRole (or (plist-get member :uiRole) "")))
          (setq poor-cli--multiplayer-state
                (plist-put poor-cli--multiplayer-state :displayName (or (plist-get member :displayName) "")))
          (setq poor-cli--multiplayer-state
                (plist-put poor-cli--multiplayer-state :approvalState (or (plist-get member :approvalState) "")))
          (setq poor-cli--multiplayer-state
                (plist-put poor-cli--multiplayer-state :handRaised (plist-get member :handRaised)))
          (setq poor-cli--multiplayer-state
                (plist-put poor-cli--multiplayer-state :queuePosition (or (plist-get member :queuePosition) 0)))))))
  (run-hooks 'poor-cli-status-changed-hook))

(defun poor-cli--apply-member-role-update (params)
  "Apply member role update PARAMS."
  (let* ((connection-id (or (plist-get params :connectionId) ""))
         (members (copy-sequence (poor-cli--normalize-seq (plist-get poor-cli--multiplayer-state :members))))
         (found nil))
    (setq members
          (mapcar
           (lambda (member)
             (if (equal (plist-get member :connectionId) connection-id)
                 (progn
                   (setq found t)
                   (plist-put (plist-put member :role (plist-get params :role))
                              :uiRole (plist-get params :uiRole)))
               member))
           members))
    (unless found
      (setq members
            (append members
                    (list (list :connectionId connection-id
                                :role (plist-get params :role)
                                :uiRole (plist-get params :uiRole))))))
    (setq poor-cli--multiplayer-state
          (plist-put poor-cli--multiplayer-state :members members))
    (when (equal connection-id (plist-get poor-cli--multiplayer-state :connectionId))
      (setq poor-cli--multiplayer-state
            (plist-put poor-cli--multiplayer-state :role (or (plist-get params :role) "")))
      (setq poor-cli--multiplayer-state
            (plist-put poor-cli--multiplayer-state :uiRole (or (plist-get params :uiRole) ""))))
    (run-hooks 'poor-cli-status-changed-hook)))

(defun poor-cli--dispatch-notification (_conn method params)
  "Handle incoming JSON-RPC METHOD with PARAMS."
  (let ((name (if (symbolp method) (symbol-name method) (format "%s" method))))
    (poor-cli--debug "Notification %s %S" name params)
    (pcase name
      ((or "poor-cli/streamChunk" "poor-cli/streamingChunk")
       (run-hook-with-args 'poor-cli-stream-chunk-hook params))
      ("poor-cli/thinkingChunk"
       (run-hook-with-args 'poor-cli-thinking-chunk-hook params))
      ("poor-cli/inlineChunk"
       (run-hook-with-args 'poor-cli-inline-chunk-hook params))
      ("poor-cli/toolEvent"
       (run-hook-with-args 'poor-cli-tool-event-hook params))
      ("poor-cli/progress"
       (run-hook-with-args 'poor-cli-progress-hook params))
      ("poor-cli/costUpdate"
       (run-hook-with-args 'poor-cli-cost-update-hook params))
      ("poor-cli/permissionReq"
       (run-hook-with-args 'poor-cli-permission-request-hook params))
      ("poor-cli/planReq"
       (run-hook-with-args 'poor-cli-plan-request-hook params))
      ("poor-cli/roomEvent"
       (poor-cli--apply-room-event params)
       (run-hook-with-args 'poor-cli-room-event-hook params))
      ("poor-cli/memberRoleUpdated"
       (poor-cli--apply-member-role-update params)
       (run-hook-with-args 'poor-cli-member-role-updated-hook params))
      ("poor-cli/suggestion"
       (setq poor-cli--multiplayer-state
             (plist-put poor-cli--multiplayer-state :lastSuggestion params))
       (run-hook-with-args 'poor-cli-suggestion-hook params))
      (_
       (poor-cli--debug "Unhandled notification %s" name)))))

(defun poor-cli--request-dispatcher (_conn method params)
  "Reject unexpected remote requests for METHOD with PARAMS."
  (jsonrpc-error :method-not-found
                 (format "Unexpected request from poor-cli server: %s" method)
                 :method (if (symbolp method) (symbol-name method) (format "%s" method))
                 :params params))

(defun poor-cli--on-shutdown (_conn)
  "Handle unexpected shutdown for the poor-cli connection."
  (let ((manual poor-cli--manual-stop))
    (setq poor-cli--connection nil
          poor-cli--capabilities nil)
    (poor-cli-set-status 'stopped (if manual "Stopped" "Server exited"))
    (unless manual
      (setq poor-cli--last-error "poor-cli server exited unexpectedly")
      (when poor-cli-auto-restart
        (setq poor-cli--restart-timer
              (run-at-time
               1 nil
               (lambda ()
                 (setq poor-cli--restart-timer nil)
                 (condition-case err
                     (progn
                       (poor-cli-start)
                       (poor-cli-initialize))
                   (error
                    (setq poor-cli--last-error err)
                    (poor-cli-set-status 'error "Auto-restart failed"))))))))))

(defun poor-cli-start ()
  "Start the poor-cli server process."
  (interactive)
  (when poor-cli--restart-timer
    (cancel-timer poor-cli--restart-timer)
    (setq poor-cli--restart-timer nil))
  (unless (poor-cli-running-p)
    (poor-cli-reset-session-state)
    (setq poor-cli--manual-stop nil
          poor-cli--stderr-buffer (get-buffer-create poor-cli-log-buffer-name)
          poor-cli--connection
          (make-instance
           'jsonrpc-process-connection
           :name "poor-cli"
           :process (lambda ()
                      (make-process
                       :name "poor-cli-server"
                       :command (poor-cli--server-command)
                       :connection-type 'pipe
                       :coding 'utf-8-emacs-unix
                       :buffer nil
                       :stderr poor-cli--stderr-buffer
                       :noquery t))
           :request-dispatcher #'poor-cli--request-dispatcher
           :notification-dispatcher #'poor-cli--dispatch-notification
           :on-shutdown #'poor-cli--on-shutdown))
    (poor-cli-set-status 'starting "Starting server"))
  poor-cli--connection)

(defun poor-cli-stop ()
  "Stop the poor-cli server."
  (interactive)
  (setq poor-cli--manual-stop t)
  (when poor-cli--restart-timer
    (cancel-timer poor-cli--restart-timer)
    (setq poor-cli--restart-timer nil))
  (when (poor-cli-running-p)
    (ignore-errors (jsonrpc-shutdown poor-cli--connection)))
  (setq poor-cli--connection nil)
  (poor-cli-reset-session-state)
  (poor-cli-set-status 'stopped "Stopped"))

(defun poor-cli-initialize ()
  "Initialize the poor-cli server for the current Emacs session."
  (interactive)
  (poor-cli-start)
  (poor-cli-set-status 'initializing "Initializing")
  (let ((result
         (jsonrpc-request
          poor-cli--connection
          (poor-cli--method "initialize")
          (list :provider poor-cli-provider
                :model poor-cli-model
                :streaming t
                :clientCapabilities (poor-cli-client-capabilities))
          :timeout poor-cli-request-timeout)))
    (poor-cli--capture-initialize-result result)
    result))

(defun poor-cli-restart ()
  "Restart and reinitialize the poor-cli server."
  (interactive)
  (poor-cli-stop)
  (poor-cli-start)
  (poor-cli-initialize))

(defun poor-cli-ensure-ready ()
  "Ensure the poor-cli server is running and initialized."
  (unless (poor-cli-running-p)
    (poor-cli-start))
  (unless poor-cli--capabilities
    (poor-cli-initialize))
  poor-cli--connection)

(defun poor-cli-request (method &optional params timeout)
  "Send a synchronous JSON-RPC METHOD with PARAMS and optional TIMEOUT."
  (poor-cli-ensure-ready)
  (setq poor-cli--last-request (list :method method :params params))
  (condition-case err
      (jsonrpc-request poor-cli--connection (poor-cli--method method) params
                       :timeout (or timeout poor-cli-request-timeout))
    (error
     (setq poor-cli--last-error err)
     (poor-cli-set-status 'error (error-message-string err))
     (signal (car err) (cdr err)))))

(defun poor-cli-request-async (method params success-fn &optional error-fn timeout)
  "Send asynchronous JSON-RPC METHOD with PARAMS.
SUCCESS-FN is called with the result plist.  ERROR-FN is called with the
error plist."
  (poor-cli-ensure-ready)
  (setq poor-cli--last-request (list :method method :params params))
  (jsonrpc-async-request
   poor-cli--connection
   (poor-cli--method method)
   params
   :success-fn (lambda (result)
                 (when success-fn
                   (funcall success-fn result)))
   :error-fn (lambda (err)
               (setq poor-cli--last-error err)
               (poor-cli-set-status 'error "Request failed")
               (when error-fn
                 (funcall error-fn err)))
   :timeout timeout))

(defun poor-cli-notify (method &optional params)
  "Send notification METHOD with PARAMS."
  (poor-cli-ensure-ready)
  (jsonrpc-notify poor-cli--connection (poor-cli--method method) params))

(defun poor-cli-cancel-logical-request (request-id)
  "Cancel a server-side REQUEST-ID if present."
  (when (and request-id (not (string-empty-p request-id)))
    (ignore-errors
      (poor-cli-request "poor-cli/cancelRequest" (list :requestId request-id) 2))))

(defun poor-cli-switch-provider (provider &optional model)
  "Switch to PROVIDER and optional MODEL."
  (poor-cli-request "poor-cli/switchProvider"
                    (list :provider provider :model model)))

(defun poor-cli-get-status-view ()
  "Return the shared backend status view."
  (poor-cli-request "poor-cli/getStatusView"))

(defun poor-cli-get-trust-view ()
  "Return the shared backend trust view."
  (poor-cli-request "poor-cli/getTrustView"))

(defun poor-cli-get-doctor-report ()
  "Return the shared backend doctor report."
  (poor-cli-request "poor-cli/getDoctorReport"))

(defun poor-cli-get-context-explain (&optional params)
  "Return the backend context explanation using PARAMS."
  (poor-cli-request "poor-cli/getContextExplain" params))

(defun poor-cli-list-runs (&optional limit)
  "Return recent shared runs with optional LIMIT."
  (poor-cli-request "poor-cli/listRuns" (list :limit (or limit 20))))

(defun poor-cli-list-workflows ()
  "Return the backend workflow list."
  (poor-cli-request "poor-cli/listWorkflows"))

(defun poor-cli-get-workflow (name)
  "Return workflow NAME."
  (poor-cli-request "poor-cli/getWorkflow" (list :name name)))

(defun poor-cli-list-tasks (&optional inbox-only limit)
  "Return durable tasks.
When INBOX-ONLY is non-nil, only actionable items are returned.
LIMIT defaults to 50."
  (poor-cli-request "poor-cli/listTasks"
                    (list :inboxOnly inbox-only :limit (or limit 50))))

(defun poor-cli-get-task (task-id)
  "Return one task by TASK-ID."
  (poor-cli-request "poor-cli/getTask" (list :taskId task-id)))

(defun poor-cli-start-task (task-id)
  "Start TASK-ID."
  (poor-cli-request "poor-cli/startTask" (list :taskId task-id)))

(defun poor-cli-approve-task (task-id &optional auto-start)
  "Approve TASK-ID and optionally AUTO-START it."
  (poor-cli-request "poor-cli/approveTask"
                    (list :taskId task-id :autoStart (if (null auto-start) t auto-start))))

(defun poor-cli-cancel-task (task-id)
  "Cancel TASK-ID."
  (poor-cli-request "poor-cli/cancelTask" (list :taskId task-id)))

(defun poor-cli-retry-task (task-id)
  "Retry TASK-ID."
  (poor-cli-request "poor-cli/retryTask" (list :taskId task-id)))

(defun poor-cli-replay-task (task-id)
  "Replay TASK-ID."
  (poor-cli-request "poor-cli/replayTask" (list :taskId task-id)))

(defun poor-cli-list-automations (&optional enabled limit)
  "Return automations filtered by ENABLED and LIMIT."
  (poor-cli-request "poor-cli/listAutomations"
                    (list :enabled enabled :limit (or limit 100))))

(defun poor-cli-get-automation (automation-id)
  "Return one automation by AUTOMATION-ID."
  (poor-cli-request "poor-cli/getAutomation" (list :automationId automation-id)))

(defun poor-cli-set-automation-enabled (automation-id enabled)
  "Set AUTOMATION-ID ENABLED state."
  (poor-cli-request "poor-cli/setAutomationEnabled"
                    (list :automationId automation-id :enabled enabled)))

(defun poor-cli-run-automation-now (automation-id)
  "Run AUTOMATION-ID immediately."
  (poor-cli-request "poor-cli/runAutomationNow" (list :automationId automation-id)))

(defun poor-cli-get-automation-history (automation-id &optional limit)
  "Return recent run history for AUTOMATION-ID."
  (poor-cli-request "poor-cli/getAutomationHistory"
                    (list :automationId automation-id :limit (or limit 25))))

(defun poor-cli-replay-automation (automation-id)
  "Replay AUTOMATION-ID."
  (poor-cli-request "poor-cli/replayAutomation" (list :automationId automation-id)))

(defun poor-cli-get-collab-summary ()
  "Return a collaboration summary payload."
  (poor-cli-request "poor-cli/getCollabSummary"))

(defun poor-cli-start-host (&optional room)
  "Start a collaboration host for ROOM."
  (poor-cli-request "poor-cli/startHostServer"
                    (when room (list :room room))))

(defun poor-cli-stop-host ()
  "Stop the active collaboration host."
  (poor-cli-request "poor-cli/stopHostServer"))

(defun poor-cli-get-host-status ()
  "Return collaboration host status."
  (poor-cli-request "poor-cli/getHostServerStatus"))

(defun poor-cli-list-host-members (&optional room)
  "Return host member snapshots for ROOM."
  (poor-cli-request "poor-cli/listHostMembers"
                    (when room (list :room room))))

(defun poor-cli-list-room-members (&optional room)
  "Return room member snapshots for ROOM."
  (poor-cli-request "poor-cli/listRoomMembers"
                    (when room (list :room room))))

(defun poor-cli-set-host-member-role (connection-id role &optional room)
  "Set CONNECTION-ID to ROLE in ROOM."
  (poor-cli-request "poor-cli/setHostMemberRole"
                    (list :connectionId connection-id :role role :room room)))

(defun poor-cli-remove-host-member (connection-id &optional room)
  "Remove CONNECTION-ID from ROOM."
  (poor-cli-request "poor-cli/removeHostMember"
                    (list :connectionId connection-id :room room)))

(defun poor-cli-approve-host-member (connection-id &optional room)
  "Approve CONNECTION-ID in ROOM."
  (poor-cli-request "poor-cli/approveHostMember"
                    (list :connectionId connection-id :room room)))

(defun poor-cli-deny-host-member (connection-id &optional room)
  "Deny CONNECTION-ID in ROOM."
  (poor-cli-request "poor-cli/denyHostMember"
                    (list :connectionId connection-id :room room)))

(defun poor-cli-set-host-lobby (enabled &optional room)
  "Set host ROOM lobby ENABLED state."
  (poor-cli-request "poor-cli/setHostLobby"
                    (list :enabled enabled :room room)))

(defun poor-cli-set-host-preset (preset &optional room)
  "Set host ROOM PRESET."
  (poor-cli-request "poor-cli/setHostPreset"
                    (list :preset preset :room room)))

(defun poor-cli-handoff-host-member (connection-id &optional room)
  "Handoff prompter control to CONNECTION-ID in ROOM."
  (poor-cli-request "poor-cli/handoffHostMember"
                    (list :connectionId connection-id :room room)))

(defun poor-cli-pass-driver (&optional connection-id room)
  "Pass driver to CONNECTION-ID in ROOM."
  (poor-cli-request "poor-cli/passDriver"
                    (list :connectionId connection-id :room room)))

(defun poor-cli-next-driver (&optional room)
  "Rotate to the next driver in ROOM."
  (poor-cli-request "poor-cli/nextDriver"
                    (when room (list :room room))))

(defun poor-cli-suggest-text (text &optional room)
  "Send TEXT suggestion in ROOM."
  (poor-cli-request "poor-cli/suggestText"
                    (list :text text :room room)))

(defun poor-cli-set-hand-raised (raised &optional room)
  "Set hand RAISED state in ROOM."
  (poor-cli-request "poor-cli/setHandRaised"
                    (list :raised raised :room room)))

(defun poor-cli-add-agenda-item (text &optional room)
  "Add agenda TEXT in ROOM."
  (poor-cli-request "poor-cli/addAgendaItem"
                    (list :text text :room room)))

(defun poor-cli-list-agenda (&optional room include-resolved)
  "Return agenda items for ROOM."
  (poor-cli-request "poor-cli/listAgenda"
                    (list :room room :includeResolved (if (null include-resolved) t include-resolved))))

(defun poor-cli-resolve-agenda-item (item-id &optional room)
  "Resolve agenda ITEM-ID in ROOM."
  (poor-cli-request "poor-cli/resolveAgendaItem"
                    (list :itemId item-id :room room)))

(defun poor-cli-list-host-activity (&optional room limit event-type)
  "Return host activity for ROOM."
  (poor-cli-request "poor-cli/listHostActivity"
                    (list :room room :limit (or limit 50) :eventType event-type)))

(provide 'poor-cli-rpc)

;;; poor-cli-rpc.el ends here

;;; poor-cli-lists.el --- Tabulated list views for poor-cli -*- lexical-binding: t; -*-

;;; Code:

(require 'pp)
(require 'subr-x)
(require 'tabulated-list)
(require 'poor-cli-rpc)

(defvar-local poor-cli-list-refresh-function nil)
(defvar-local poor-cli-list-title nil)

(define-derived-mode poor-cli-tabulated-mode tabulated-list-mode "PoorCLI-List"
  "Base tabulated list mode for poor-cli views.")

(defun poor-cli-lists--show-detail (title payload)
  "Open TITLE displaying PAYLOAD."
  (let ((buffer (get-buffer-create title)))
    (with-current-buffer buffer
      (let ((inhibit-read-only t))
        (erase-buffer)
        (insert (pp-to-string payload))
        (goto-char (point-min))
        (special-mode)))
    (display-buffer buffer poor-cli-chat-display-action)))

(defun poor-cli-lists-refresh ()
  "Refresh the current poor-cli tabulated list."
  (interactive)
  (setq tabulated-list-entries (funcall poor-cli-list-refresh-function))
  (tabulated-list-print t))

(defun poor-cli-lists-current-payload ()
  "Return the payload for the current tabulated list row."
  (tabulated-list-get-id))

(defun poor-cli-lists-view-entry ()
  "Show the current row payload."
  (interactive)
  (let ((payload (poor-cli-lists-current-payload)))
    (when payload
      (poor-cli-lists--show-detail
       (format "*poor-cli %s detail*" (or poor-cli-list-title "entry"))
       payload))))

(define-key poor-cli-tabulated-mode-map (kbd "g") #'poor-cli-lists-refresh)
(define-key poor-cli-tabulated-mode-map (kbd "RET") #'poor-cli-lists-view-entry)

(defun poor-cli-lists--open (buffer-name title columns refresh-fn &optional extra-bindings)
  "Open BUFFER-NAME using TITLE, COLUMNS, REFRESH-FN, and EXTRA-BINDINGS."
  (let ((buffer (get-buffer-create buffer-name)))
    (with-current-buffer buffer
      (poor-cli-tabulated-mode)
      (setq poor-cli-list-title title
            poor-cli-list-refresh-function refresh-fn
            tabulated-list-format columns
            tabulated-list-padding 2)
      (remove-hook 'tabulated-list-revert-hook #'poor-cli-lists-refresh t)
      (add-hook 'tabulated-list-revert-hook #'poor-cli-lists-refresh nil t)
      (tabulated-list-init-header)
      (use-local-map
       (let ((map (copy-keymap poor-cli-tabulated-mode-map)))
         (dolist (binding extra-bindings)
           (define-key map (kbd (car binding)) (cdr binding)))
         map))
      (poor-cli-lists-refresh))
    (display-buffer buffer poor-cli-chat-display-action)
    buffer))

(defun poor-cli-lists--runs-entries ()
  "Return tabulated entries for the recent run list."
  (mapcar
   (lambda (run)
     (list run
           (vector
            (or (plist-get run :runId) "")
            (or (plist-get run :status) "")
            (format "%s/%s" (or (plist-get run :sourceKind) "") (or (plist-get run :sourceId) ""))
            (or (plist-get run :summary) ""))))
   (poor-cli--normalize-seq (plist-get (poor-cli-list-runs 30) :runs))))

(defun poor-cli-lists-open-runs ()
  "Open the run history view."
  (interactive)
  (poor-cli-lists--open
   poor-cli-runs-buffer-name
   "runs"
   [("Run ID" 24 t) ("Status" 14 t) ("Source" 26 t) ("Summary" 0 t)]
   #'poor-cli-lists--runs-entries))

(defun poor-cli-lists--task-entries (&optional inbox-only)
  "Return entries for durable tasks.  When INBOX-ONLY, limit to actionable tasks."
  (mapcar
   (lambda (task)
     (list task
           (vector
            (or (plist-get task :taskId) "")
            (or (plist-get task :status) "")
            (or (plist-get task :title) "")
            (or (plist-get task :source) "")
            (or (poor-cli--get-in task :metadata :lastRunId) ""))))
   (poor-cli--normalize-seq
    (plist-get (poor-cli-list-tasks inbox-only 100) :tasks))))

(defun poor-cli-lists-task-approve ()
  "Approve the current task."
  (interactive)
  (when-let* ((task (poor-cli-lists-current-payload))
              (task-id (plist-get task :taskId)))
    (poor-cli-approve-task task-id)
    (poor-cli-lists-refresh)))

(defun poor-cli-lists-task-start ()
  "Start the current task."
  (interactive)
  (when-let* ((task (poor-cli-lists-current-payload))
              (task-id (plist-get task :taskId)))
    (poor-cli-start-task task-id)
    (poor-cli-lists-refresh)))

(defun poor-cli-lists-task-cancel ()
  "Cancel the current task."
  (interactive)
  (when-let* ((task (poor-cli-lists-current-payload))
              (task-id (plist-get task :taskId)))
    (poor-cli-cancel-task task-id)
    (poor-cli-lists-refresh)))

(defun poor-cli-lists-task-retry ()
  "Retry the current task."
  (interactive)
  (when-let* ((task (poor-cli-lists-current-payload))
              (task-id (plist-get task :taskId)))
    (poor-cli-retry-task task-id)
    (poor-cli-lists-refresh)))

(defun poor-cli-lists-task-replay ()
  "Replay the current task."
  (interactive)
  (when-let* ((task (poor-cli-lists-current-payload))
              (task-id (plist-get task :taskId)))
    (poor-cli-replay-task task-id)
    (poor-cli-lists-refresh)))

(defun poor-cli-lists-open-tasks (&optional inbox-only)
  "Open the task list.  When INBOX-ONLY, show only actionable tasks."
  (interactive)
  (poor-cli-lists--open
   poor-cli-tasks-buffer-name
   "tasks"
   [("Task ID" 18 t) ("Status" 14 t) ("Title" 30 t) ("Source" 14 t) ("Last Run" 18 t)]
   (lambda () (poor-cli-lists--task-entries inbox-only))
   '(("a" . poor-cli-lists-task-approve)
     ("s" . poor-cli-lists-task-start)
     ("c" . poor-cli-lists-task-cancel)
     ("r" . poor-cli-lists-task-retry)
     ("p" . poor-cli-lists-task-replay))))

(defun poor-cli-lists--automation-entries ()
  "Return entries for automations."
  (mapcar
   (lambda (automation)
     (list automation
           (vector
            (or (plist-get automation :automationId) "")
            (if (plist-get automation :enabled) "enabled" "disabled")
            (or (plist-get automation :name) "")
            (or (plist-get automation :executionMode) "worktree")
            (or (plist-get automation :nextRunAt) "")
            (or (plist-get automation :lastRunStatus) ""))))
   (poor-cli--normalize-seq
    (plist-get (poor-cli-list-automations nil 100) :automations))))

(defun poor-cli-lists-automation-toggle ()
  "Toggle the current automation."
  (interactive)
  (when-let* ((automation (poor-cli-lists-current-payload))
              (automation-id (plist-get automation :automationId)))
    (poor-cli-set-automation-enabled automation-id (not (plist-get automation :enabled)))
    (poor-cli-lists-refresh)))

(defun poor-cli-lists-automation-run-now ()
  "Run the current automation immediately."
  (interactive)
  (when-let* ((automation (poor-cli-lists-current-payload))
              (automation-id (plist-get automation :automationId)))
    (poor-cli-run-automation-now automation-id)
    (poor-cli-lists-refresh)))

(defun poor-cli-lists-automation-replay ()
  "Replay the current automation."
  (interactive)
  (when-let* ((automation (poor-cli-lists-current-payload))
              (automation-id (plist-get automation :automationId)))
    (poor-cli-replay-automation automation-id)
    (poor-cli-lists-refresh)))

(defun poor-cli-lists-automation-history ()
  "Open recent history for the current automation."
  (interactive)
  (when-let* ((automation (poor-cli-lists-current-payload))
              (automation-id (plist-get automation :automationId))
              (payload (poor-cli-get-automation-history automation-id 25)))
    (poor-cli-lists--show-detail
     (format "*poor-cli automation %s history*" automation-id)
     payload)))

(defun poor-cli-lists-open-automations ()
  "Open the automation list."
  (interactive)
  (poor-cli-lists--open
   poor-cli-automations-buffer-name
   "automations"
   [("Automation ID" 18 t) ("Enabled" 10 t) ("Name" 26 t) ("Mode" 10 t) ("Next Run" 24 t) ("Last Status" 14 t)]
   #'poor-cli-lists--automation-entries
   '(("e" . poor-cli-lists-automation-toggle)
     ("r" . poor-cli-lists-automation-run-now)
     ("R" . poor-cli-lists-automation-replay)
     ("h" . poor-cli-lists-automation-history))))

(defun poor-cli-lists--member-entries (payload)
  "Return member entries from PAYLOAD."
  (let* ((rooms (poor-cli--normalize-seq (plist-get payload :rooms)))
         (room-payloads
          (if rooms
              rooms
            (list (list :name (or (plist-get payload :room) "")
                        :members (plist-get payload :members))))))
    (apply
     #'append
     (mapcar
      (lambda (room-payload)
        (let ((room-name (or (plist-get room-payload :name)
                             (plist-get room-payload :room)
                             "")))
          (mapcar
           (lambda (member)
             (let ((row (plist-put (copy-sequence member) :room room-name)))
               (list row
                     (vector
                      room-name
                      (or (plist-get row :connectionId) "")
                      (or (plist-get row :displayName) "")
                      (or (plist-get row :role) "")
                      (or (plist-get row :approvalState) "")
                      (if (plist-get row :handRaised) "yes" "no")))))
           (poor-cli--normalize-seq (plist-get room-payload :members)))))
      room-payloads))))

(defun poor-cli-lists-members-remove ()
  "Remove the current collaboration member."
  (interactive)
  (when-let* ((member (poor-cli-lists-current-payload))
              (connection-id (plist-get member :connectionId)))
    (poor-cli-remove-host-member connection-id (plist-get member :room))
    (poor-cli-lists-refresh)))

(defun poor-cli-lists-members-approve ()
  "Approve the current collaboration member."
  (interactive)
  (when-let* ((member (poor-cli-lists-current-payload))
              (connection-id (plist-get member :connectionId)))
    (poor-cli-approve-host-member connection-id (plist-get member :room))
    (poor-cli-lists-refresh)))

(defun poor-cli-lists-members-deny ()
  "Deny the current collaboration member."
  (interactive)
  (when-let* ((member (poor-cli-lists-current-payload))
              (connection-id (plist-get member :connectionId)))
    (poor-cli-deny-host-member connection-id (plist-get member :room))
    (poor-cli-lists-refresh)))

(defun poor-cli-lists-members-set-viewer ()
  "Set the current collaboration member to viewer."
  (interactive)
  (when-let* ((member (poor-cli-lists-current-payload))
              (connection-id (plist-get member :connectionId)))
    (poor-cli-set-host-member-role connection-id "viewer" (plist-get member :room))
    (poor-cli-lists-refresh)))

(defun poor-cli-lists-members-set-prompter ()
  "Set the current collaboration member to prompter."
  (interactive)
  (when-let* ((member (poor-cli-lists-current-payload))
              (connection-id (plist-get member :connectionId)))
    (poor-cli-set-host-member-role connection-id "prompter" (plist-get member :room))
    (poor-cli-lists-refresh)))

(defun poor-cli-lists-members-handoff ()
  "Handoff the current collaboration member to prompter."
  (interactive)
  (when-let* ((member (poor-cli-lists-current-payload))
              (connection-id (plist-get member :connectionId)))
    (poor-cli-handoff-host-member connection-id (plist-get member :room))
    (poor-cli-lists-refresh)))

(defun poor-cli-lists-members-pass-driver ()
  "Pass driver to the current collaboration member."
  (interactive)
  (when-let* ((member (poor-cli-lists-current-payload))
              (connection-id (plist-get member :connectionId)))
    (poor-cli-pass-driver connection-id (plist-get member :room))
    (poor-cli-lists-refresh)))

(defun poor-cli-lists-open-members (&optional room joined)
  "Open the collaboration member list.
When ROOM is non-nil, scope the member list to that room.
When JOINED is non-nil, inspect the joined room instead of the local host."
  (interactive)
  (poor-cli-lists--open
   poor-cli-members-buffer-name
   "members"
   [("Room" 12 t) ("Connection" 18 t) ("Display" 18 t) ("Role" 12 t) ("Approval" 12 t) ("Hand" 6 t)]
   (lambda ()
     (poor-cli-lists--member-entries
      (if joined
          (poor-cli-list-room-members room)
        (poor-cli-list-host-members room))))
   (if joined
       '(("p" . poor-cli-lists-members-pass-driver))
     '(("k" . poor-cli-lists-members-remove)
       ("a" . poor-cli-lists-members-approve)
       ("d" . poor-cli-lists-members-deny)
       ("v" . poor-cli-lists-members-set-viewer)
       ("p" . poor-cli-lists-members-set-prompter)
       ("h" . poor-cli-lists-members-handoff)))))

(defun poor-cli-lists--agenda-entries (&optional room)
  "Return entries for the collaboration agenda."
  (let* ((payload (poor-cli-list-agenda room t))
         (room-name (or (plist-get payload :room) room "")))
    (mapcar
     (lambda (item)
       (let ((row (plist-put (copy-sequence item) :room room-name)))
         (list row
               (vector
                (format "%s" (or (plist-get row :id) ""))
                (if (plist-get row :resolved) "resolved" "open")
                (or (plist-get row :author) "")
                (or (plist-get row :text) "")))))
     (poor-cli--normalize-seq (plist-get payload :items)))))

(defun poor-cli-lists-agenda-resolve ()
  "Resolve the current agenda item."
  (interactive)
  (when-let* ((item (poor-cli-lists-current-payload))
              (item-id (plist-get item :id)))
    (poor-cli-resolve-agenda-item item-id (plist-get item :room))
    (poor-cli-lists-refresh)))

(defun poor-cli-lists-open-agenda (&optional room)
  "Open the collaboration agenda."
  (interactive)
  (poor-cli-lists--open
   poor-cli-agenda-buffer-name
   "agenda"
   [("ID" 8 t) ("State" 10 t) ("Author" 14 t) ("Text" 0 t)]
   (lambda () (poor-cli-lists--agenda-entries room))
   '(("x" . poor-cli-lists-agenda-resolve))))

(defun poor-cli-lists--activity-entries (&optional room)
  "Return entries for collaboration activity."
  (mapcar
   (lambda (event)
     (list event
           (vector
            (or (plist-get event :timestamp) "")
            (or (plist-get event :eventType) "")
            (or (plist-get event :actor) "")
            (format "%s" (or (plist-get event :details) "")))))
   (poor-cli--normalize-seq
    (plist-get (poor-cli-list-host-activity room 50 nil) :events))))

(defun poor-cli-lists-open-activity (&optional room)
  "Open collaboration activity."
  (interactive)
  (poor-cli-lists--open
   poor-cli-activity-buffer-name
   "activity"
   [("Timestamp" 24 t) ("Event" 18 t) ("Actor" 18 t) ("Details" 0 t)]
   (lambda () (poor-cli-lists--activity-entries room))))

(provide 'poor-cli-lists)

;;; poor-cli-lists.el ends here

;;; poor-cli-sessions.el --- Session management for poor-cli -*- lexical-binding: t; -*-

;;; Code:

(require 'subr-x)
(require 'poor-cli-rpc)
(require 'poor-cli-lists)

(defun poor-cli-create-session-rpc (&optional params)
  "Create a new session."
  (poor-cli-request "poor-cli/createSession" params))

(defun poor-cli-list-mux-sessions (&optional params)
  "Return mux sessions."
  (poor-cli-request "poor-cli/listMuxSessions" params))

(defun poor-cli-switch-session-rpc (params)
  "Switch to a session with PARAMS."
  (poor-cli-request "poor-cli/switchSession" params))

(defun poor-cli-fork-session-rpc (params)
  "Fork a session with PARAMS."
  (poor-cli-request "poor-cli/forkSession" params))

(defun poor-cli-destroy-session-rpc (params)
  "Destroy a session with PARAMS."
  (poor-cli-request "poor-cli/destroySession" params))

(defun poor-cli-rename-session-rpc (params)
  "Rename a session with PARAMS."
  (poor-cli-request "poor-cli/renameSession" params))

(defun poor-cli-save-session-rpc (params)
  "Save a session with PARAMS."
  (poor-cli-request "poor-cli/saveSession" params))

(defun poor-cli-restore-session-rpc (params)
  "Restore a session with PARAMS."
  (poor-cli-request "poor-cli/restoreSession" params))

(defun poor-cli-sessions--entries ()
  "Return tabulated entries for sessions."
  (mapcar
   (lambda (session)
     (list session
           (vector
            (or (plist-get session :id) "")
            (or (plist-get session :label) "")
            (if (plist-get session :active) "yes" "no")
            (format "%s" (or (plist-get session :messages) 0)))))
   (poor-cli--normalize-seq (plist-get (poor-cli-list-mux-sessions) :sessions))))

(defun poor-cli-sessions--switch ()
  "Switch to the session at point."
  (interactive)
  (when-let* ((session (poor-cli-lists-current-payload))
              (id (plist-get session :id)))
    (poor-cli-switch-session-rpc (list :id id))
    (poor-cli-lists-refresh)))

(defun poor-cli-session-create ()
  "Create a new session."
  (interactive)
  (let ((label (read-string "Session label: ")))
    (poor-cli-create-session-rpc (list :label label))
    (message "[poor-cli] Session created")))

(defun poor-cli-session-fork ()
  "Fork the session at point."
  (interactive)
  (when-let* ((session (poor-cli-lists-current-payload))
              (id (plist-get session :id)))
    (poor-cli-fork-session-rpc (list :id id))
    (poor-cli-lists-refresh)))

(defun poor-cli-session-destroy ()
  "Destroy the session at point."
  (interactive)
  (when-let* ((session (poor-cli-lists-current-payload))
              (id (plist-get session :id)))
    (poor-cli-destroy-session-rpc (list :id id))
    (poor-cli-lists-refresh)))

(defun poor-cli-session-rename ()
  "Rename the session at point."
  (interactive)
  (when-let* ((session (poor-cli-lists-current-payload))
              (id (plist-get session :id)))
    (let ((label (read-string "New label: ")))
      (poor-cli-rename-session-rpc (list :id id :label label))
      (poor-cli-lists-refresh))))

(defun poor-cli-session-save ()
  "Save the session at point."
  (interactive)
  (when-let* ((session (poor-cli-lists-current-payload))
              (id (plist-get session :id)))
    (poor-cli-save-session-rpc (list :id id))
    (message "[poor-cli] Session saved")))

(defun poor-cli-session-restore ()
  "Restore the session at point."
  (interactive)
  (when-let* ((session (poor-cli-lists-current-payload))
              (id (plist-get session :id)))
    (poor-cli-restore-session-rpc (list :id id))
    (poor-cli-lists-refresh)))

(defun poor-cli-sessions-open ()
  "Open the session list."
  (interactive)
  (poor-cli-lists--open
   poor-cli-sessions-buffer-name
   "sessions"
   [("ID" 18 t) ("Label" 24 t) ("Active" 8 t) ("Messages" 10 t)]
   #'poor-cli-sessions--entries
   '(("RET" . poor-cli-sessions--switch)
     ("f" . poor-cli-session-fork)
     ("d" . poor-cli-session-destroy)
     ("r" . poor-cli-session-rename)
     ("s" . poor-cli-session-save)
     ("R" . poor-cli-session-restore)
     ("c" . poor-cli-session-create))))

(provide 'poor-cli-sessions)

;;; poor-cli-sessions.el ends here

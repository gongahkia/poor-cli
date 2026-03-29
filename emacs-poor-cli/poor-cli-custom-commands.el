;;; poor-cli-custom-commands.el --- Custom commands for poor-cli -*- lexical-binding: t; -*-

;;; Code:

(require 'subr-x)
(require 'poor-cli-rpc)
(require 'poor-cli-lists)

(defun poor-cli-list-custom-commands (&optional params)
  "Return custom commands."
  (poor-cli-request "poor-cli/listCustomCommands" params))

(defun poor-cli-get-custom-command (params)
  "Get a custom command with PARAMS."
  (poor-cli-request "poor-cli/getCustomCommand" params))

(defun poor-cli-run-custom-command-rpc (params)
  "Run a custom command with PARAMS."
  (poor-cli-request "poor-cli/runCustomCommand" params))

(defun poor-cli-custom-commands--entries ()
  "Return tabulated entries for custom commands."
  (mapcar
   (lambda (cmd)
     (list cmd
           (vector
            (or (plist-get cmd :name) "")
            (or (plist-get cmd :description) "")
            (truncate-string-to-width (or (plist-get cmd :template) "") 40 nil nil t))))
   (poor-cli--normalize-seq (plist-get (poor-cli-list-custom-commands) :commands))))

(defun poor-cli-custom-command-run ()
  "Run the custom command at point."
  (interactive)
  (when-let* ((cmd (poor-cli-lists-current-payload))
              (name (plist-get cmd :name)))
    (poor-cli-run-custom-command-rpc (list :name name))
    (message "[poor-cli] Custom command %s executed" name)))

(defun poor-cli-custom-command--inspect ()
  "Inspect the custom command at point."
  (interactive)
  (when-let* ((cmd (poor-cli-lists-current-payload))
              (name (plist-get cmd :name)))
    (poor-cli-lists--show-detail
     (format "*poor-cli command %s*" name)
     (poor-cli-get-custom-command (list :name name)))))

(defun poor-cli-custom-commands-open ()
  "Open the custom commands list."
  (interactive)
  (poor-cli-lists--open
   poor-cli-custom-commands-buffer-name
   "custom-commands"
   [("Name" 20 t) ("Description" 30 t) ("Template" 0 t)]
   #'poor-cli-custom-commands--entries
   '(("RET" . poor-cli-custom-command-run)
     ("i" . poor-cli-custom-command--inspect))))

(provide 'poor-cli-custom-commands)

;;; poor-cli-custom-commands.el ends here

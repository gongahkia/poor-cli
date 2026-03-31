;;; poor-cli-history.el --- Conversation history for poor-cli -*- lexical-binding: t; -*-

;;; Code:

(require 'subr-x)
(require 'poor-cli-rpc)
(require 'poor-cli-lists)

(defun poor-cli-list-history (&optional params)
  "Return conversation history."
  (poor-cli-request "poor-cli/listHistory" params))

(defun poor-cli-search-history-rpc (params)
  "Search conversation history with PARAMS."
  (poor-cli-request "poor-cli/searchHistory" params))

(defun poor-cli-export-conversation-rpc (params)
  "Export a conversation with PARAMS."
  (poor-cli-request "poor-cli/exportConversation" params))

(defun poor-cli-history--entries ()
  "Return tabulated entries for history."
  (mapcar
   (lambda (entry)
     (list entry
           (vector
            (or (plist-get entry :id) "")
            (or (plist-get entry :date) "")
            (truncate-string-to-width (or (plist-get entry :preview) "") 40 nil nil t)
            (format "%s" (or (plist-get entry :messages) 0)))))
   (poor-cli--normalize-seq (plist-get (poor-cli-list-history) :entries))))

(defun poor-cli-history-search ()
  "Search conversation history."
  (interactive)
  (let* ((query (read-string "Search history: "))
         (result (poor-cli-search-history-rpc (list :query query))))
    (poor-cli-lists--show-detail "*poor-cli history search*" result)))

(defun poor-cli-export-conversation ()
  "Export the conversation at point."
  (interactive)
  (when-let* ((entry (poor-cli-lists-current-payload))
              (id (plist-get entry :id)))
    (poor-cli-lists--show-detail
     (format "*poor-cli export %s*" id)
     (poor-cli-export-conversation-rpc (list :id id)))))

(defun poor-cli-history-open ()
  "Open the history list."
  (interactive)
  (poor-cli-lists--open
   poor-cli-history-buffer-name
   "history"
   [("ID" 18 t) ("Date" 20 t) ("Preview" 40 t) ("Messages" 10 t)]
   #'poor-cli-history--entries
   '(("/" . poor-cli-history-search)
     ("e" . poor-cli-export-conversation))))

(provide 'poor-cli-history)

;;; poor-cli-history.el ends here

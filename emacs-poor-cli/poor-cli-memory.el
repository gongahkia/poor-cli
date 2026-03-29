;;; poor-cli-memory.el --- Memory management for poor-cli -*- lexical-binding: t; -*-

;;; Code:

(require 'subr-x)
(require 'poor-cli-rpc)
(require 'poor-cli-lists)

(defun poor-cli-memory-list (&optional params)
  "Return memory entries."
  (poor-cli-request "poor-cli/memoryList" params))

(defun poor-cli-memory-save-rpc (params)
  "Save a memory entry with PARAMS."
  (poor-cli-request "poor-cli/memorySave" params))

(defun poor-cli-memory-search-rpc (params)
  "Search memory with PARAMS."
  (poor-cli-request "poor-cli/memorySearch" params))

(defun poor-cli-memory-delete-rpc (params)
  "Delete a memory entry with PARAMS."
  (poor-cli-request "poor-cli/memoryDelete" params))

(defun poor-cli-memory--entries ()
  "Return tabulated entries for memory."
  (mapcar
   (lambda (entry)
     (list entry
           (vector
            (or (plist-get entry :key) "")
            (truncate-string-to-width (or (plist-get entry :value) "") 40 nil nil t)
            (or (plist-get entry :updated) ""))))
   (poor-cli--normalize-seq (plist-get (poor-cli-memory-list) :entries))))

(defun poor-cli-memory-save ()
  "Save a memory key-value pair."
  (interactive)
  (let ((key (read-string "Key: "))
        (value (read-string "Value: ")))
    (poor-cli-memory-save-rpc (list :key key :value value))
    (message "[poor-cli] Memory saved")))

(defun poor-cli-memory-search ()
  "Search memory by query."
  (interactive)
  (let* ((query (read-string "Search: "))
         (result (poor-cli-memory-search-rpc (list :query query))))
    (poor-cli-lists--show-detail "*poor-cli memory search*" result)))

(defun poor-cli-memory-delete ()
  "Delete the memory entry at point."
  (interactive)
  (when-let* ((entry (poor-cli-lists-current-payload))
              (key (plist-get entry :key)))
    (poor-cli-memory-delete-rpc (list :key key))
    (poor-cli-lists-refresh)))

(defun poor-cli-memory-open ()
  "Open the memory list."
  (interactive)
  (poor-cli-lists--open
   poor-cli-memory-buffer-name
   "memory"
   [("Key" 24 t) ("Value" 40 t) ("Updated" 24 t)]
   #'poor-cli-memory--entries
   '(("s" . poor-cli-memory-save)
     ("/" . poor-cli-memory-search)
     ("d" . poor-cli-memory-delete))))

(provide 'poor-cli-memory)

;;; poor-cli-memory.el ends here

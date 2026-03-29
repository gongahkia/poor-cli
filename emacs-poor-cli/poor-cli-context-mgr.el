;;; poor-cli-context-mgr.el --- Context management for poor-cli -*- lexical-binding: t; -*-

;;; Code:

(require 'subr-x)
(require 'markdown-mode)
(require 'poor-cli-rpc)
(require 'poor-cli-lists)

(defun poor-cli-preview-context-rpc (&optional params)
  "Return context preview."
  (poor-cli-request "poor-cli/previewContext" params))

(defun poor-cli-compact-context-rpc (&optional params)
  "Compact context."
  (poor-cli-request "poor-cli/compactContext" params))

(defun poor-cli-preview-mutation-rpc (&optional params)
  "Preview a mutation."
  (poor-cli-request "poor-cli/previewMutation" params))

(defun poor-cli-context-preview ()
  "Open a markdown buffer with context preview."
  (interactive)
  (let* ((payload (poor-cli-preview-context-rpc))
         (content (or (plist-get payload :preview) (pp-to-string payload)))
         (buffer (get-buffer-create "*poor-cli context preview*")))
    (with-current-buffer buffer
      (markdown-mode)
      (let ((inhibit-read-only t))
        (erase-buffer)
        (insert content)
        (goto-char (point-min))
        (read-only-mode 1)))
    (display-buffer buffer poor-cli-chat-display-action)))

(defun poor-cli-context-compact ()
  "Compact the current context."
  (interactive)
  (poor-cli-compact-context-rpc)
  (message "[poor-cli] Context compacted"))

(defun poor-cli-mutation-preview ()
  "Preview the pending mutation."
  (interactive)
  (poor-cli-lists--show-detail
   "*poor-cli mutation preview*"
   (poor-cli-preview-mutation-rpc)))

(provide 'poor-cli-context-mgr)

;;; poor-cli-context-mgr.el ends here

;;; poor-cli-review.el --- Plan and permission review buffers -*- lexical-binding: t; -*-

;;; Code:

(require 'cl-lib)
(require 'button)
(require 'subr-x)
(require 'poor-cli-rpc)

(defvar-local poor-cli-review-kind nil)
(defvar-local poor-cli-review-prompt-id nil)
(defvar-local poor-cli-review-request-id nil)

(define-derived-mode poor-cli-review-mode special-mode "PoorCLI-Review"
  "Major mode for poor-cli review buffers.")

(defun poor-cli-review--open-buffer (title)
  "Open review buffer with TITLE."
  (let ((buffer (get-buffer-create poor-cli-review-buffer-name)))
    (with-current-buffer buffer
      (poor-cli-review-mode)
      (let ((inhibit-read-only t))
        (erase-buffer)
        (setq poor-cli-review-kind nil
              poor-cli-review-prompt-id nil
              poor-cli-review-request-id nil)
        (insert title "\n\n")))
    (display-buffer buffer poor-cli-chat-display-action)
    buffer))

(defun poor-cli-review--insert-actions ()
  "Insert approve/reject buttons in the current review buffer."
  (insert-text-button
   "[Approve]"
   'action (lambda (_button) (poor-cli-review-approve))
   'follow-link t)
  (insert "  ")
  (insert-text-button
   "[Reject]"
   'action (lambda (_button) (poor-cli-review-reject))
   'follow-link t)
  (insert "\n\n")
  (insert "Keys: `a` approve, `r` reject.\n\n"))

(defun poor-cli-review-open-permission (params)
  "Open a permission review buffer from PARAMS."
  (let ((buffer (poor-cli-review--open-buffer "# poor-cli permission review")))
    (with-current-buffer buffer
      (setq poor-cli-review-kind 'permission
            poor-cli-review-prompt-id (plist-get params :promptId)
            poor-cli-review-request-id (plist-get params :requestId))
      (let ((inhibit-read-only t))
        (poor-cli-review--insert-actions)
        (insert (format "- Tool: `%s`\n" (or (plist-get params :toolName) "")))
        (insert (format "- Operation: `%s`\n" (or (plist-get params :operation) "")))
        (insert (format "- Sandbox preset: `%s`\n" (or (plist-get params :sandboxPreset) "")))
        (when-let ((message (plist-get params :message)))
          (unless (string-empty-p message)
            (insert (format "- Message: %s\n" message))))
        (when-let ((checkpoint-id (plist-get params :checkpointId)))
          (insert (format "- Checkpoint: `%s`\n" checkpoint-id)))
        (when-let ((paths (poor-cli--normalize-seq (plist-get params :paths))))
          (when paths
            (insert "- Paths:\n")
            (dolist (path paths)
              (insert (format "  - `%s`\n" path)))))
        (when-let ((capabilities (plist-get params :capabilities)))
          (insert (format "- Capabilities: `%S`\n" capabilities)))
        (when-let ((diff (plist-get params :diff)))
          (unless (string-empty-p diff)
            (insert "\n## Diff Preview\n\n```diff\n")
            (insert diff)
            (unless (string-suffix-p "\n" diff)
              (insert "\n"))
            (insert "```\n"))))
      (goto-char (point-min)))
    buffer))

(defun poor-cli-review-open-plan (params)
  "Open a plan review buffer from PARAMS."
  (let ((buffer (poor-cli-review--open-buffer "# poor-cli plan review")))
    (with-current-buffer buffer
      (setq poor-cli-review-kind 'plan
            poor-cli-review-prompt-id (plist-get params :promptId)
            poor-cli-review-request-id (plist-get params :requestId))
      (let ((inhibit-read-only t))
        (poor-cli-review--insert-actions)
        (insert (format "## Summary\n\n%s\n\n" (or (plist-get params :summary) "")))
        (insert "## Original Request\n\n")
        (insert (or (plist-get params :originalRequest) ""))
        (insert "\n\n## Steps\n\n")
        (cl-loop for step across (vconcat (poor-cli--normalize-seq (plist-get params :steps)))
                 for index from 1 do
                 (insert (format "%d. %s\n" index step)))))
    (display-buffer buffer poor-cli-chat-display-action)
    buffer))

(defun poor-cli-review--send-decision (allowed)
  "Send ALLOWED decision for the current review buffer."
  (pcase poor-cli-review-kind
    ('permission
     (poor-cli-notify "poor-cli/permissionRes"
                      (list :promptId poor-cli-review-prompt-id
                            :allowed allowed
                            :approvedPaths []
                            :approvedChunks [])))
    ('plan
     (poor-cli-notify "poor-cli/planRes"
                      (list :promptId poor-cli-review-prompt-id
                            :allowed allowed))))
  (let ((inhibit-read-only t))
    (goto-char (point-max))
    (insert (format "\nDecision: %s\n" (if allowed "approved" "rejected"))))
  (message "[poor-cli] %s %s"
           (capitalize (symbol-name poor-cli-review-kind))
           (if allowed "approved" "rejected")))

(defun poor-cli-review-approve ()
  "Approve the current review buffer."
  (interactive)
  (poor-cli-review--send-decision t))

(defun poor-cli-review-reject ()
  "Reject the current review buffer."
  (interactive)
  (poor-cli-review--send-decision nil))

(define-key poor-cli-review-mode-map (kbd "a") #'poor-cli-review-approve)
(define-key poor-cli-review-mode-map (kbd "r") #'poor-cli-review-reject)

(add-hook 'poor-cli-permission-request-hook #'poor-cli-review-open-permission)
(add-hook 'poor-cli-plan-request-hook #'poor-cli-review-open-plan)

(provide 'poor-cli-review)

;;; poor-cli-review.el ends here

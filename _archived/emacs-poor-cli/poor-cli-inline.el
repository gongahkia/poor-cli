;;; poor-cli-inline.el --- Overlay inline completion for poor-cli -*- lexical-binding: t; -*-

;;; Code:

(require 'cl-lib)
(require 'subr-x)
(require 'poor-cli-rpc)

(defvar-local poor-cli-inline--overlay nil)
(defvar-local poor-cli-inline--request-id nil)
(defvar-local poor-cli-inline--completion-text "")
(defvar-local poor-cli-inline--idle-timer nil)

(defun poor-cli-inline--file-extension ()
  "Return the current file extension, or an empty string."
  (downcase (or (file-name-extension (or buffer-file-name "")) "")))

(defun poor-cli-inline-eligible-p ()
  "Return non-nil when poor-cli inline completion is eligible in this buffer."
  (and (bound-and-true-p poor-cli-mode)
       poor-cli-completion-enabled
       (not (minibufferp))
       (not (member major-mode poor-cli-completion-major-mode-blocklist))
       (let ((ext (poor-cli-inline--file-extension)))
         (and (or (null poor-cli-completion-filetype-allowlist)
                  (member ext poor-cli-completion-filetype-allowlist))
              (not (member ext poor-cli-completion-filetype-blocklist))))))

(defun poor-cli-inline--clear-idle-timer ()
  "Cancel the current inline idle timer."
  (when (timerp poor-cli-inline--idle-timer)
    (cancel-timer poor-cli-inline--idle-timer)
    (setq poor-cli-inline--idle-timer nil)))

(defun poor-cli-inline-dismiss ()
  "Dismiss the current inline completion."
  (interactive)
  (poor-cli-inline--clear-idle-timer)
  (when poor-cli-inline--request-id
    (poor-cli-cancel-logical-request poor-cli-inline--request-id))
  (setq poor-cli--current-inline-request-id nil
        poor-cli-inline--request-id nil
        poor-cli-inline--completion-text "")
  (when (overlayp poor-cli-inline--overlay)
    (delete-overlay poor-cli-inline--overlay)
    (setq poor-cli-inline--overlay nil)))

(defun poor-cli-inline--render-overlay ()
  "Render the current inline overlay."
  (if (or (null poor-cli-inline--completion-text)
          (string-empty-p poor-cli-inline--completion-text))
      (poor-cli-inline-dismiss)
    (unless (overlayp poor-cli-inline--overlay)
      (setq poor-cli-inline--overlay (make-overlay (point) (point) nil t t)))
    (move-overlay poor-cli-inline--overlay (point) (point))
    (overlay-put poor-cli-inline--overlay 'after-string
                 (propertize poor-cli-inline--completion-text 'face 'shadow))))

(defun poor-cli-inline--clamp-string (text)
  "Clamp TEXT to `poor-cli-completion-max-chars'."
  (if (> (length text) poor-cli-completion-max-chars)
      (substring text 0 poor-cli-completion-max-chars)
    text))

(defun poor-cli-inline--context ()
  "Return the inline completion request payload for the current point."
  (let* ((before-start (save-excursion
                         (forward-line (- poor-cli-completion-context-lines-before))
                         (point)))
         (after-end (save-excursion
                      (forward-line poor-cli-completion-context-lines-after)
                      (line-end-position)))
         (before (buffer-substring-no-properties before-start (point)))
         (after (buffer-substring-no-properties (point) after-end)))
    (list :codeBefore (poor-cli-inline--clamp-string before)
          :codeAfter (poor-cli-inline--clamp-string after)
          :filePath (or buffer-file-name "")
          :language (symbol-name major-mode)
          :provider poor-cli-completion-provider
          :model poor-cli-completion-model)))

(defun poor-cli-inline-trigger (&optional instruction)
  "Trigger inline completion with optional INSTRUCTION."
  (interactive)
  (unless (poor-cli-inline-eligible-p)
    (user-error "poor-cli inline completion is disabled in this buffer"))
  (poor-cli-inline-dismiss)
  (poor-cli-ensure-ready)
  (let ((request-id (poor-cli--uuidish-id "inline"))
        (payload (poor-cli-inline--context)))
    (setq poor-cli-inline--request-id request-id
          poor-cli--current-inline-request-id request-id
          poor-cli-inline--completion-text "")
    (setq payload (plist-put payload :requestId request-id))
    (setq payload (plist-put payload :streamPartial t))
    (when (and instruction (not (string-empty-p instruction)))
      (setq payload (plist-put payload :instruction instruction)))
    (poor-cli-request-async
     "poor-cli/inlineComplete"
     payload
     (lambda (result)
       (when (and (equal request-id poor-cli-inline--request-id)
                  (string-empty-p poor-cli-inline--completion-text))
         (setq poor-cli-inline--request-id nil
               poor-cli--current-inline-request-id nil)
         (setq poor-cli-inline--completion-text (or (plist-get result :completion) ""))
         (poor-cli-inline--render-overlay)))
     (lambda (_err)
       (when (equal request-id poor-cli-inline--request-id)
         (poor-cli-inline-dismiss)))
     nil)))

(defun poor-cli-inline--consume (piece)
  "Insert PIECE and consume it from the current inline completion."
  (insert piece)
  (setq poor-cli-inline--completion-text
        (string-remove-prefix piece poor-cli-inline--completion-text))
  (poor-cli-inline--render-overlay))

(defun poor-cli-inline-accept ()
  "Accept the full inline completion."
  (interactive)
  (unless (string-empty-p poor-cli-inline--completion-text)
    (poor-cli-inline--consume poor-cli-inline--completion-text)))

(defun poor-cli-inline-accept-line ()
  "Accept the current inline completion line."
  (interactive)
  (when (and poor-cli-inline--completion-text
             (not (string-empty-p poor-cli-inline--completion-text)))
    (let* ((index (or (string-match "\n" poor-cli-inline--completion-text)
                      (length poor-cli-inline--completion-text)))
           (piece (substring poor-cli-inline--completion-text 0 index)))
      (poor-cli-inline--consume piece))))

(defun poor-cli-inline-accept-word ()
  "Accept the next word from the inline completion."
  (interactive)
  (when (and poor-cli-inline--completion-text
             (not (string-empty-p poor-cli-inline--completion-text)))
    (let ((piece
           (if (string-match "\\`\\([[:space:]]*[^[:space:]\n]*\\)" poor-cli-inline--completion-text)
               (match-string 1 poor-cli-inline--completion-text)
             poor-cli-inline--completion-text)))
      (poor-cli-inline--consume piece))))

(defun poor-cli-inline--handle-chunk (params)
  "Handle inline chunk PARAMS."
  (when (equal (plist-get params :requestId) poor-cli-inline--request-id)
    (if (plist-get params :done)
        (setq poor-cli-inline--request-id nil
              poor-cli--current-inline-request-id nil)
      (setq poor-cli-inline--completion-text
            (concat poor-cli-inline--completion-text (or (plist-get params :chunk) "")))
      (poor-cli-inline--render-overlay))))

(defun poor-cli-inline--schedule ()
  "Schedule an idle inline completion request."
  (poor-cli-inline--clear-idle-timer)
  (when (and (poor-cli-inline-eligible-p)
             (not poor-cli-completion-manual-only))
    (let ((buffer (current-buffer)))
      (setq poor-cli-inline--idle-timer
            (run-with-idle-timer
             poor-cli-completion-idle-delay nil
             (lambda ()
               (when (buffer-live-p buffer)
                 (with-current-buffer buffer
                   (when (and (bound-and-true-p poor-cli-mode)
                              (not poor-cli-inline--request-id))
                     (ignore-errors (poor-cli-inline-trigger)))))))))))

(defun poor-cli-inline-post-command ()
  "Post-command hook used for auto-triggered inline completion."
  (unless poor-cli-completion-manual-only
    (when (and (poor-cli-inline-eligible-p)
               (or (eq this-command 'self-insert-command)
                   (eq this-command 'newline)))
      (poor-cli-inline--schedule))))

(defun poor-cli-inline-enable-buffer ()
  "Enable inline completion hooks for the current buffer."
  (add-hook 'post-command-hook #'poor-cli-inline-post-command nil t))

(defun poor-cli-inline-disable-buffer ()
  "Disable inline completion hooks for the current buffer."
  (remove-hook 'post-command-hook #'poor-cli-inline-post-command t)
  (poor-cli-inline-dismiss))

(add-hook 'poor-cli-inline-chunk-hook #'poor-cli-inline--handle-chunk)

(provide 'poor-cli-inline)

;;; poor-cli-inline.el ends here

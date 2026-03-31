;;; poor-cli-chat.el --- Chat transcript and streaming UI for poor-cli -*- lexical-binding: t; -*-

;;; Code:

(require 'cl-lib)
(require 'subr-x)
(require 'markdown-mode)
(require 'poor-cli-rpc)

(defvar poor-cli-chat--active-buffer nil)
(defvar poor-cli-chat--active-request-id nil)
(defvar poor-cli-chat--stream-marker nil)

(define-derived-mode poor-cli-chat-mode markdown-mode "PoorCLI-Chat"
  "Major mode for the poor-cli transcript."
  (read-only-mode 1))

(defun poor-cli-chat--buffer ()
  "Return the chat buffer, creating it if needed."
  (or (and (buffer-live-p poor-cli-chat--active-buffer) poor-cli-chat--active-buffer)
      (setq poor-cli-chat--active-buffer (get-buffer-create poor-cli-chat-buffer-name))))

(defun poor-cli-chat-open ()
  "Display the chat transcript buffer."
  (interactive)
  (let ((buffer (poor-cli-chat--buffer)))
    (with-current-buffer buffer
      (unless (derived-mode-p 'poor-cli-chat-mode)
        (poor-cli-chat-mode))
      (setq-local truncate-lines nil))
    (display-buffer buffer poor-cli-chat-display-action)
    buffer))

(defun poor-cli-chat-toggle ()
  "Toggle the chat transcript buffer."
  (interactive)
  (let ((buffer (poor-cli-chat--buffer)))
    (if-let ((window (get-buffer-window buffer)))
        (delete-window window)
      (poor-cli-chat-open))))

(defun poor-cli-chat--insert (text)
  "Insert TEXT at the end of the chat buffer."
  (with-current-buffer (poor-cli-chat-open)
    (let ((inhibit-read-only t))
      (goto-char (point-max))
      (insert text))
    (goto-char (point-max))))

(defun poor-cli-chat-append-message (role text)
  "Append ROLE and TEXT to the chat transcript."
  (poor-cli-chat--insert
   (format "## %s\n\n%s\n\n"
           (capitalize role)
           text)))

(defun poor-cli-chat-clear ()
  "Clear chat history locally and on the backend."
  (interactive)
  (poor-cli-request "poor-cli/clearHistory")
  (with-current-buffer (poor-cli-chat-open)
    (let ((inhibit-read-only t))
      (erase-buffer)))
  (setq poor-cli-chat--active-request-id nil
        poor-cli-chat--stream-marker nil))

(defun poor-cli-chat-cancel ()
  "Cancel the active streaming chat request."
  (interactive)
  (when poor-cli-chat--active-request-id
    (poor-cli-cancel-logical-request poor-cli-chat--active-request-id)
    (setq poor-cli-chat--active-request-id nil)
    (message "[poor-cli] Cancelled chat request")))

(defun poor-cli-chat--begin-response (message request-id)
  "Create a new transcript block for MESSAGE with REQUEST-ID."
  (setq poor-cli-chat--active-request-id request-id
        poor-cli--current-chat-request-id request-id)
  (with-current-buffer (poor-cli-chat-open)
    (let ((inhibit-read-only t))
      (goto-char (point-max))
      (insert (format "## User\n\n%s\n\n## Assistant\n\n" message))
      (setq poor-cli-chat--stream-marker (point-marker)))))

(defun poor-cli-chat--finalize-response (request-id)
  "Finalize the current response for REQUEST-ID."
  (when (and poor-cli-chat--stream-marker
             (equal request-id poor-cli-chat--active-request-id))
    (with-current-buffer (poor-cli-chat-open)
      (let ((inhibit-read-only t))
        (goto-char (point-max))
        (insert "\n\n---\n\n")))
    (setq poor-cli-chat--active-request-id nil
          poor-cli--current-chat-request-id nil
          poor-cli-chat--stream-marker nil)))

(defun poor-cli-chat-send (message &optional context-files)
  "Send MESSAGE through streaming chat with optional CONTEXT-FILES."
  (interactive (list (read-string "poor-cli prompt: ")))
  (unless (and (stringp message) (not (string-empty-p message)))
    (user-error "Message is required"))
  (poor-cli-ensure-ready)
  (let ((request-id (poor-cli--uuidish-id "chat")))
    (poor-cli-chat--begin-response message request-id)
    (poor-cli-request-async
     "poor-cli/chatStreaming"
     (list :message message
           :contextFiles context-files
           :requestId request-id)
     (lambda (_result)
       (poor-cli-chat--finalize-response request-id))
     (lambda (err)
       (poor-cli-chat--insert (format "\n\nError: %S\n" err))
       (poor-cli-chat--finalize-response request-id))
     nil)))

(defun poor-cli-chat-send-region (beg end)
  "Send region between BEG and END to chat."
  (interactive "r")
  (unless (use-region-p)
    (user-error "Active region required"))
  (let* ((language (symbol-name major-mode))
         (text (buffer-substring-no-properties beg end))
         (prompt (read-string "Instruction: " "Explain this selection."))
         (message (format "%s\n\n```%s\n%s\n```" prompt language text)))
    (poor-cli-chat-send message (when buffer-file-name (list buffer-file-name)))))

(defun poor-cli-chat-send-buffer ()
  "Send the current buffer to chat."
  (interactive)
  (let* ((language (symbol-name major-mode))
         (text (buffer-substring-no-properties (point-min) (point-max)))
         (prompt (read-string "Instruction: " "Summarize this buffer."))
         (message (format "%s\n\n```%s\n%s\n```" prompt language text)))
    (poor-cli-chat-send message (when buffer-file-name (list buffer-file-name)))))

(defun poor-cli-chat-send-file (file)
  "Send FILE contents to chat."
  (interactive "fSend file: ")
  (let* ((file (expand-file-name file))
         (text (with-temp-buffer
                 (insert-file-contents file)
                 (buffer-string)))
         (language (or (file-name-extension file) "text"))
         (prompt (read-string "Instruction: " "Summarize this file."))
         (message (format "%s\n\n```%s\n%s\n```" prompt language text)))
    (poor-cli-chat-send message (list file))))

(defun poor-cli-chat--handle-stream (params)
  "Handle streaming PARAMS."
  (let ((request-id (plist-get params :requestId)))
    (when (and poor-cli-chat--stream-marker
               (equal request-id poor-cli-chat--active-request-id))
      (if (plist-get params :done)
          (poor-cli-chat--finalize-response request-id)
        (with-current-buffer (poor-cli-chat-open)
          (let ((inhibit-read-only t))
            (goto-char poor-cli-chat--stream-marker)
            (insert (or (plist-get params :chunk) ""))
            (set-marker poor-cli-chat--stream-marker (point))))))))

(defun poor-cli-chat--handle-thinking (params)
  "Render thinking PARAMS into the chat transcript."
  (let ((request-id (plist-get params :requestId))
        (chunk (plist-get params :chunk)))
    (when (and poor-cli-chat--stream-marker
               (equal request-id poor-cli-chat--active-request-id)
               (stringp chunk)
               (not (string-empty-p chunk)))
      (with-current-buffer (poor-cli-chat-open)
        (let ((inhibit-read-only t))
          (goto-char poor-cli-chat--stream-marker)
          (insert (format "> Thinking: %s\n" (string-trim chunk)))
          (set-marker poor-cli-chat--stream-marker (point)))))))

(defun poor-cli-chat--handle-tool-event (params)
  "Render tool event PARAMS into the chat transcript."
  (let ((request-id (plist-get params :requestId))
        (event-type (plist-get params :eventType))
        (tool-name (plist-get params :toolName)))
    (when (and poor-cli-chat--stream-marker
               (equal request-id poor-cli-chat--active-request-id))
      (with-current-buffer (poor-cli-chat-open)
        (let ((inhibit-read-only t))
          (goto-char poor-cli-chat--stream-marker)
          (insert (format "- %s `%s`\n"
                          (capitalize (replace-regexp-in-string "_" " " (or event-type "")))
                          (or tool-name "")))
          (when-let ((message (plist-get params :message)))
            (unless (string-empty-p message)
              (insert (format "  %s\n" message))))
          (set-marker poor-cli-chat--stream-marker (point)))))))

(defun poor-cli-chat--handle-progress (params)
  "Render progress PARAMS into the chat transcript."
  (let ((request-id (plist-get params :requestId)))
    (when (and poor-cli-chat--stream-marker
               (equal request-id poor-cli-chat--active-request-id))
      (with-current-buffer (poor-cli-chat-open)
        (let ((inhibit-read-only t))
          (goto-char poor-cli-chat--stream-marker)
          (insert (format "- Progress `%s`: %s\n"
                          (or (plist-get params :phase) "")
                          (or (plist-get params :message) "")))
          (set-marker poor-cli-chat--stream-marker (point)))))))

(defun poor-cli-chat--handle-suggestion (params)
  "Render collaboration suggestion PARAMS into the chat transcript."
  (when-let ((text (plist-get params :text)))
    (poor-cli-chat-append-message
     "suggestion"
     (format "%s\n\nFrom `%s`"
             text
             (or (plist-get params :sender) "collaborator")))))

(add-hook 'poor-cli-stream-chunk-hook #'poor-cli-chat--handle-stream)
(add-hook 'poor-cli-thinking-chunk-hook #'poor-cli-chat--handle-thinking)
(add-hook 'poor-cli-tool-event-hook #'poor-cli-chat--handle-tool-event)
(add-hook 'poor-cli-progress-hook #'poor-cli-chat--handle-progress)
(add-hook 'poor-cli-suggestion-hook #'poor-cli-chat--handle-suggestion)

(provide 'poor-cli-chat)

;;; poor-cli-chat.el ends here

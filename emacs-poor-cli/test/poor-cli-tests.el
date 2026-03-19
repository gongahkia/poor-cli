;;; poor-cli-tests.el --- ERT coverage for poor-cli Emacs client -*- lexical-binding: t; -*-

(require 'ert)
(require 'cl-lib)
(require 'poor-cli)

(ert-deftest poor-cli-client-capabilities-declare-emacs-surface ()
  (let ((caps (poor-cli-client-capabilities)))
    (should (equal (plist-get caps :uiSurface) "emacs"))
    (should (plist-get (plist-get caps :reviewFlows) :permissionRequests))
    (should (plist-get (plist-get caps :multiplayer) :events))))

(ert-deftest poor-cli-client-status-is-available-without-shadowing-command-name ()
  (poor-cli-reset-session-state)
  (let ((status (poor-cli-client-status)))
    (should (eq (plist-get status :state) 'stopped))
    (should (equal (plist-get status :message) "Stopped"))))

(ert-deftest poor-cli-capture-initialize-result-updates-state ()
  (poor-cli-reset-session-state)
  (poor-cli--capture-initialize-result
   '(:capabilities (:providerInfo (:name "ollama" :model "llama3")
                   :multiplayer (:enabled t
                                 :room "dev"
                                 :role "prompter"
                                 :connectionId "abc123"))))
  (should (equal poor-cli--status-state 'ready))
  (should (equal (plist-get poor-cli--multiplayer-state :room) "dev"))
  (should (equal (plist-get poor-cli--multiplayer-state :connectionId) "abc123")))

(ert-deftest poor-cli-dispatch-room-event-updates-multiplayer-state ()
  (poor-cli-reset-session-state)
  (setq poor-cli--multiplayer-state
        (plist-put poor-cli--multiplayer-state :connectionId "abc123"))
  (poor-cli--dispatch-notification
   nil 'poor-cli/roomEvent
   '(:room "dev"
     :memberCount 2
     :queueDepth 1
     :members ((:connectionId "abc123" :role "viewer" :displayName "me" :approvalState "approved"))))
  (should (equal (plist-get poor-cli--multiplayer-state :room) "dev"))
  (should (= (plist-get poor-cli--multiplayer-state :memberCount) 2))
  (should (equal (plist-get poor-cli--multiplayer-state :role) "viewer")))

(ert-deftest poor-cli-inline-eligible-respects-filters ()
  (with-temp-buffer
    (setq-local poor-cli-mode t)
    (setq-local buffer-file-name "/tmp/example.py")
    (let ((poor-cli-completion-enabled t)
          (poor-cli-completion-filetype-allowlist '("py"))
          (poor-cli-completion-filetype-blocklist nil)
          (poor-cli-completion-major-mode-blocklist nil))
      (should (poor-cli-inline-eligible-p)))
    (let ((poor-cli-completion-enabled t)
          (poor-cli-completion-filetype-allowlist '("js"))
          (poor-cli-completion-filetype-blocklist nil)
          (poor-cli-completion-major-mode-blocklist nil))
      (should-not (poor-cli-inline-eligible-p)))))

(ert-deftest poor-cli-inline-accept-word-consumes-prefix ()
  (with-temp-buffer
    (setq-local poor-cli-inline--completion-text " world\nnext")
    (poor-cli-inline-accept-word)
    (should (equal (buffer-string) " world"))
    (should (equal poor-cli-inline--completion-text "\nnext"))))

(ert-deftest poor-cli-chat-stream-handler-appends-response ()
  (let ((buffer (poor-cli-chat-open)))
    (with-current-buffer buffer
      (let ((inhibit-read-only t))
        (erase-buffer)))
    (poor-cli-chat--begin-response "hello" "chat-1")
    (poor-cli-chat--handle-stream '(:requestId "chat-1" :chunk "world" :done nil))
    (poor-cli-chat--handle-stream '(:requestId "chat-1" :chunk "" :done t))
    (with-current-buffer buffer
      (should (string-match-p "world" (buffer-string)))
      (should (string-match-p "---" (buffer-string))))))

(ert-deftest poor-cli-review-approve-sends-notification ()
  (let (captured)
    (with-temp-buffer
      (poor-cli-review-mode)
      (setq-local poor-cli-review-kind 'permission
                  poor-cli-review-prompt-id "prompt-1")
      (cl-letf (((symbol-function 'poor-cli-notify)
                 (lambda (method params)
                   (setq captured (list method params)))))
        (poor-cli-review-approve)))
    (should (equal (car captured) "poor-cli/permissionRes"))
    (should (equal (plist-get (cadr captured) :promptId) "prompt-1"))
    (should (plist-get (cadr captured) :allowed))))

(ert-deftest poor-cli-lists-runs-build-tabulated-entries ()
  (cl-letf (((symbol-function 'poor-cli-list-runs)
             (lambda (&optional _limit)
               '(:runs ((:runId "run-1"
                        :status "completed"
                        :sourceKind "task"
                        :sourceId "abc"
                        :summary "done"))))))
    (let ((entries (poor-cli-lists--runs-entries)))
      (should (= (length entries) 1))
      (should (equal (aref (cadr (car entries)) 0) "run-1")))))

(ert-deftest poor-cli-lists-member-entries-retain-room-context ()
  (let* ((payload '(:rooms ((:name "dev"
                             :members ((:connectionId "a1" :displayName "Alice")))
                            (:name "docs"
                             :members ((:connectionId "b2" :displayName "Bob"))))))
         (entries (poor-cli-lists--member-entries payload))
         (first-row (car entries))
         (second-row (cadr entries)))
    (should (= (length entries) 2))
    (should (equal (plist-get (car first-row) :room) "dev"))
    (should (equal (aref (cadr first-row) 0) "dev"))
    (should (equal (plist-get (car second-row) :room) "docs"))
    (should (equal (aref (cadr second-row) 0) "docs"))))

(ert-deftest poor-cli-lists-member-pass-driver-propagates-room ()
  (let (captured)
    (with-temp-buffer
      (poor-cli-tabulated-mode)
      (setq tabulated-list-format [("Room" 12 t) ("Connection" 18 t) ("Display" 18 t)
                                   ("Role" 12 t) ("Approval" 12 t) ("Hand" 6 t)])
      (tabulated-list-init-header)
      (setq tabulated-list-entries
            (list (list '(:connectionId "abc123" :room "dev")
                        ["dev" "abc123" "Alice" "viewer" "approved" "no"])))
      (tabulated-list-print)
      (goto-char (point-min))
      (forward-line 1)
      (cl-letf (((symbol-function 'poor-cli-pass-driver)
                 (lambda (&optional connection-id room)
                   (setq captured (list connection-id room))))
                ((symbol-function 'poor-cli-lists-refresh)
                 #'ignore))
        (poor-cli-lists-members-pass-driver)))
    (should (equal captured '("abc123" "dev")))))

(ert-deftest poor-cli-collab-share-payload-extracts-invite ()
  (let* ((payload '(:rooms ((:name "dev"
                            :viewerInviteCode "viewer-token"
                            :prompterInviteCode "prompter-token"))))
         (share (poor-cli-collab--share-payload payload "viewer" "dev")))
    (should (equal (plist-get share :invite) "viewer-token"))
    (should (equal (plist-get share :room) "dev"))))

(ert-deftest poor-cli-collab-set-hand-raised-requires-joined-session ()
  (poor-cli-reset-session-state)
  (should-error (poor-cli-collab-set-hand-raised t) :type 'user-error))

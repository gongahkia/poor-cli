;;; poor-cli-collab.el --- Collaboration commands for poor-cli -*- lexical-binding: t; -*-

;;; Code:

(require 'pp)
(require 'seq)
(require 'subr-x)
(require 'markdown-mode)
(require 'transient)
(require 'poor-cli-lists)

(defun poor-cli-collab--open-markdown (name content)
  "Open markdown buffer NAME with CONTENT."
  (let ((buffer (get-buffer-create name)))
    (with-current-buffer buffer
      (markdown-mode)
      (let ((inhibit-read-only t))
        (erase-buffer)
        (insert content)
        (goto-char (point-min))
        (read-only-mode 1)))
    (display-buffer buffer poor-cli-chat-display-action)))

(defun poor-cli-collab-current-room ()
  "Return the current collaboration room name, if any."
  (let ((room (plist-get poor-cli--multiplayer-state :room)))
    (unless (string-empty-p (or room ""))
      room)))

(defun poor-cli-collab--host-room-names ()
  "Return available local host room names."
  (mapcar
   (lambda (room) (or (plist-get room :name) ""))
   (poor-cli--normalize-seq (plist-get (poor-cli-get-host-status) :rooms))))

(defun poor-cli-collab--resolve-room (&optional prompt)
  "Return the active collaboration room, prompting with PROMPT when needed."
  (or (poor-cli-collab-current-room)
      (let* ((rooms (seq-filter
                     (lambda (name) (not (string-empty-p (or name ""))))
                     (poor-cli-collab--host-room-names))))
        (pcase (length rooms)
          (0 nil)
          (1 (car rooms))
          (_ (completing-read (or prompt "Room: ") rooms nil t))))))

(defun poor-cli-collab--room-payload (payload room-name)
  "Return ROOM-NAME payload from host status PAYLOAD."
  (seq-find
   (lambda (room)
     (equal (plist-get room :name) room-name))
   (poor-cli--normalize-seq (plist-get payload :rooms))))

(defun poor-cli-collab--share-payload (payload role room-name)
  "Extract share PAYLOAD for ROLE in ROOM-NAME."
  (let* ((room (poor-cli-collab--room-payload payload room-name))
         (invite-key (if (equal role "viewer") :viewerInviteCode :prompterInviteCode)))
    (when room
      (list :room (or (plist-get room :name) room-name)
            :role role
            :invite (or (plist-get room invite-key) "")))))

(defun poor-cli-collab-start (&optional room preset)
  "Start collaboration host with ROOM and PRESET."
  (interactive)
  (let* ((room (or room (read-string "Room: " "dev")))
         (preset (or preset (completing-read "Preset: " '("pairing" "mob" "review") nil t nil nil "mob")))
         (payload (poor-cli-start-host room)))
    (poor-cli-set-host-preset preset room)
    (poor-cli-collab--open-markdown
     "*poor-cli-collab*"
     (format "# collaboration host\n\nStarted room `%s` with preset `%s`.\n\n```lisp\n%s```\n"
             room preset (pp-to-string payload)))))

(defun poor-cli-collab-stop ()
  "Stop the active collaboration host."
  (interactive)
  (poor-cli-stop-host)
  (message "[poor-cli] Collaboration host stopped"))

(defun poor-cli-collab-join (invite)
  "Join a collaboration session using signed INVITE."
  (interactive "sInvite: ")
  (setq poor-cli-multiplayer-invite invite)
  (poor-cli-restart)
  (message "[poor-cli] Joined collaboration via invite"))

(defun poor-cli-collab-leave ()
  "Leave the active collaboration bridge session."
  (interactive)
  (setq poor-cli-multiplayer-invite nil)
  (poor-cli-restart)
  (message "[poor-cli] Left collaboration session"))

(defun poor-cli-collab-summary ()
  "Open the collaboration summary buffer."
  (interactive)
  (let* ((payload (poor-cli-get-collab-summary))
         (collab (plist-get payload :collaboration)))
    (poor-cli-collab--open-markdown
     "*poor-cli-collab-summary*"
     (mapconcat
      #'identity
      (list "# collaboration summary"
            ""
            (format "- Running: `%s`" (plist-get collab :running))
            (format "- Role: `%s`" (or (plist-get collab :role) "solo"))
            (format "- Room: `%s`" (or (plist-get collab :room) ""))
            (format "- Members: %s" (or (plist-get collab :memberCount) 0))
            (format "- Queue depth: %s" (or (poor-cli--get-in collab :queueState :depth) 0))
            (format "- Hands raised: %s" (or (poor-cli--get-in collab :queueState :handsRaised) 0))
            (format "- Health: `%s`" (or (plist-get collab :connectionHealth) "unknown"))
            (format "- Summary: %s" (or (plist-get collab :summary) "")))
      "\n"))))

(defun poor-cli-collab-members ()
  "Open collaboration members.
Uses joined room members when attached to a room, otherwise host members."
  (interactive)
  (let ((room (poor-cli-collab--resolve-room)))
    (poor-cli-lists-open-members room (and room (not (null (poor-cli-collab-current-room)))))))

(defun poor-cli-collab-share (role)
  "Copy a viewer or prompter invite for ROLE."
  (interactive (list (completing-read "Role: " '("viewer" "prompter") nil t nil nil "prompter")))
  (let* ((payload (poor-cli-get-host-status))
         (rooms (poor-cli--normalize-seq (plist-get payload :rooms)))
         (_ (unless rooms
              (user-error "No active host rooms are available")))
         (room-name (if (= (length rooms) 1)
                        (plist-get (car rooms) :name)
                      (completing-read "Room: "
                                       (mapcar (lambda (room) (plist-get room :name)) rooms)
                                       nil t)))
         (share (poor-cli-collab--share-payload payload role room-name)))
    (unless share
      (user-error "No invite found for room %s" room-name))
    (kill-new (plist-get share :invite))
    (message "[poor-cli] Copied %s invite for room %s" role room-name)))

(defun poor-cli-collab-pass-driver (&optional target)
  "Pass driver to TARGET."
  (interactive)
  (let ((target (or target (read-string "Connection or member id (empty for next): ")))
        (room (poor-cli-collab--resolve-room)))
    (poor-cli-pass-driver (unless (string-empty-p target) target)
                          room)
    (message "[poor-cli] Driver updated")))

(defun poor-cli-collab-next-driver ()
  "Rotate to the next driver."
  (interactive)
  (poor-cli-next-driver (poor-cli-collab--resolve-room))
  (message "[poor-cli] Driver rotated"))

(defun poor-cli-collab-suggest (text)
  "Send collaboration suggestion TEXT."
  (interactive "sSuggestion: ")
  (poor-cli-suggest-text text (poor-cli-collab--resolve-room))
  (message "[poor-cli] Suggestion sent"))

(defun poor-cli-collab-set-hand-raised (raised)
  "Set hand RAISED state in the current room."
  (interactive)
  (let ((connection-id (plist-get poor-cli--multiplayer-state :connectionId)))
    (unless (and (stringp connection-id) (not (string-empty-p connection-id)))
      (user-error "Hand raise is only available for an active joined collaboration session"))
    (poor-cli-set-hand-raised raised (poor-cli-collab--resolve-room))
    (message "[poor-cli] Hand %s" (if raised "raised" "lowered"))))

(defun poor-cli-collab-add-agenda (text)
  "Add agenda item TEXT."
  (interactive "sAgenda item: ")
  (let ((room (poor-cli-collab--resolve-room)))
    (poor-cli-add-agenda-item text room)
    (poor-cli-lists-open-agenda room)))

(defun poor-cli-collab-open-agenda ()
  "Open the collaboration agenda."
  (interactive)
  (poor-cli-lists-open-agenda (poor-cli-collab--resolve-room)))

(defun poor-cli-collab-open-activity ()
  "Open collaboration activity."
  (interactive)
  (poor-cli-lists-open-activity (poor-cli-collab--resolve-room)))

(defun poor-cli-collab-set-lobby (enabled)
  "Set collaboration host lobby ENABLED."
  (interactive)
  (poor-cli-set-host-lobby enabled (poor-cli-collab--resolve-room))
  (message "[poor-cli] Lobby %s" (if enabled "enabled" "disabled")))

(defun poor-cli-collab-set-preset (preset)
  "Set collaboration PRESET."
  (interactive (list (completing-read "Preset: " '("pairing" "mob" "review") nil t)))
  (poor-cli-set-host-preset preset (poor-cli-collab--resolve-room))
  (message "[poor-cli] Collaboration preset set to %s" preset))

(defun poor-cli-collab--handle-suggestion (params)
  "Show transient suggestion notice for PARAMS."
  (message "[poor-cli] Suggestion from %s: %s"
           (or (plist-get params :sender) "collaborator")
           (or (plist-get params :text) "")))

(add-hook 'poor-cli-suggestion-hook #'poor-cli-collab--handle-suggestion)

(transient-define-prefix poor-cli-collab-dispatch ()
  "Collaboration command menu."
  [["Session"
    ("s" "Start host" poor-cli-collab-start)
    ("j" "Join invite" poor-cli-collab-join)
    ("l" "Leave bridge" poor-cli-collab-leave)
    ("x" "Stop host" poor-cli-collab-stop)]
   ["Inspect"
    ("u" "Summary" poor-cli-collab-summary)
    ("m" "Members" poor-cli-collab-members)
    ("a" "Agenda" poor-cli-collab-open-agenda)
    ("y" "Activity" poor-cli-collab-open-activity)]]
  [["Control"
    ("p" "Pass driver" poor-cli-collab-pass-driver)
    ("n" "Next driver" poor-cli-collab-next-driver)
    ("g" "Suggest text" poor-cli-collab-suggest)
    ("h" "Raise hand" (lambda () (interactive) (poor-cli-collab-set-hand-raised t)))
    ("H" "Lower hand" (lambda () (interactive) (poor-cli-collab-set-hand-raised nil)))]
   ["Host"
    ("v" "Share viewer" (lambda () (interactive) (poor-cli-collab-share "viewer")))
    ("P" "Share prompter" (lambda () (interactive) (poor-cli-collab-share "prompter")))
    ("L" "Lobby on" (lambda () (interactive) (poor-cli-collab-set-lobby t)))
    ("O" "Lobby off" (lambda () (interactive) (poor-cli-collab-set-lobby nil)))
    ("r" "Preset" poor-cli-collab-set-preset)
    ("+" "Agenda add" poor-cli-collab-add-agenda)]])

(provide 'poor-cli-collab)

;;; poor-cli-collab.el ends here

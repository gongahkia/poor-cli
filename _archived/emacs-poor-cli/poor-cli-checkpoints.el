;;; poor-cli-checkpoints.el --- Checkpoint management for poor-cli -*- lexical-binding: t; -*-

;;; Code:

(require 'subr-x)
(require 'poor-cli-rpc)
(require 'poor-cli-lists)

(defun poor-cli-list-checkpoints (&optional params)
  "Return checkpoints."
  (poor-cli-request "poor-cli/listCheckpoints" params))

(defun poor-cli-create-checkpoint (params)
  "Create a checkpoint with PARAMS."
  (poor-cli-request "poor-cli/createCheckpoint" params))

(defun poor-cli-restore-checkpoint (params)
  "Restore a checkpoint with PARAMS."
  (poor-cli-request "poor-cli/restoreCheckpoint" params))

(defun poor-cli-preview-checkpoint (params)
  "Preview a checkpoint with PARAMS."
  (poor-cli-request "poor-cli/previewCheckpoint" params))

(defun poor-cli-gc-checkpoints (&optional params)
  "Garbage collect old checkpoints."
  (poor-cli-request "poor-cli/gcCheckpoints" params))

(defun poor-cli-checkpoints--entries ()
  "Return tabulated entries for checkpoints."
  (mapcar
   (lambda (cp)
     (list cp
           (vector
            (or (plist-get cp :id) "")
            (or (plist-get cp :label) "")
            (or (plist-get cp :created) "")
            (format "%s" (or (plist-get cp :files) 0)))))
   (poor-cli--normalize-seq (plist-get (poor-cli-list-checkpoints) :checkpoints))))

(defun poor-cli-checkpoints--restore ()
  "Restore the checkpoint at point."
  (interactive)
  (when-let* ((cp (poor-cli-lists-current-payload))
              (id (plist-get cp :id)))
    (poor-cli-restore-checkpoint (list :id id))
    (poor-cli-lists-refresh)))

(defun poor-cli-checkpoints--preview ()
  "Preview the checkpoint at point."
  (interactive)
  (when-let* ((cp (poor-cli-lists-current-payload))
              (id (plist-get cp :id)))
    (poor-cli-lists--show-detail
     (format "*poor-cli checkpoint %s*" id)
     (poor-cli-preview-checkpoint (list :id id)))))

(defun poor-cli-checkpoint-create ()
  "Create a new checkpoint with a label."
  (interactive)
  (let ((label (read-string "Checkpoint label: ")))
    (poor-cli-create-checkpoint (list :label label))
    (message "[poor-cli] Checkpoint created")))

(defun poor-cli-checkpoint-gc ()
  "Garbage collect old checkpoints."
  (interactive)
  (poor-cli-gc-checkpoints)
  (message "[poor-cli] Checkpoint GC complete"))

(defun poor-cli-checkpoints-open ()
  "Open the checkpoint list."
  (interactive)
  (poor-cli-lists--open
   poor-cli-checkpoints-buffer-name
   "checkpoints"
   [("ID" 18 t) ("Label" 24 t) ("Created" 24 t) ("Files" 8 t)]
   #'poor-cli-checkpoints--entries
   '(("r" . poor-cli-checkpoints--restore)
     ("p" . poor-cli-checkpoints--preview)
     ("c" . poor-cli-checkpoint-create)
     ("g" . poor-cli-checkpoint-gc))))

(provide 'poor-cli-checkpoints)

;;; poor-cli-checkpoints.el ends here

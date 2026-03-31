;;; poor-cli.el --- Vanilla Emacs client for poor-cli -*- lexical-binding: t; -*-

;; Package-Requires: ((emacs "29.1") (markdown-mode "2.6") (transient "0.4.0"))

;;; Commentary:

;; First-party Emacs integration for poor-cli using the shared stdio JSON-RPC
;; server.

;;; Code:

(require 'poor-cli-state)
(require 'poor-cli-rpc)
(require 'poor-cli-review)
(require 'poor-cli-chat)
(require 'poor-cli-inline)
(require 'poor-cli-lists)
(require 'poor-cli-collab)
(require 'poor-cli-commands)
(require 'poor-cli-checkpoints)
(require 'poor-cli-memory)
(require 'poor-cli-sessions)
(require 'poor-cli-agents)
(require 'poor-cli-config)
(require 'poor-cli-history)
(require 'poor-cli-custom-commands)
(require 'poor-cli-skills)
(require 'poor-cli-trust-mgr)
(require 'poor-cli-context-mgr)
(require 'poor-cli-cost)
(require 'poor-cli-providers)

(defvar poor-cli-mode-map
  (let ((map (make-sparse-keymap)))
    (define-key map (kbd "C-c p p") #'poor-cli-dispatch)
    (define-key map (kbd "C-c p c") #'poor-cli-chat-open)
    (define-key map (kbd "C-c p s") #'poor-cli-chat-send)
    (define-key map (kbd "C-c p i") #'poor-cli-inline-trigger)
    (define-key map (kbd "C-c p a") #'poor-cli-inline-accept)
    (define-key map (kbd "C-c p d") #'poor-cli-inline-dismiss)
    (define-key map (kbd "C-c p t") #'poor-cli-trust)
    (define-key map (kbd "C-c p m") #'poor-cli-collab-dispatch)
    map)
  "Keymap for `poor-cli-mode'.")

(define-minor-mode poor-cli-mode
  "Buffer-local poor-cli integration."
  :lighter " poor-cli"
  :keymap poor-cli-mode-map
  (if poor-cli-mode
      (progn
        (poor-cli-inline-enable-buffer)
        (when poor-cli-auto-start
          (ignore-errors
            (poor-cli-start)
            (poor-cli-initialize))))
    (poor-cli-inline-disable-buffer)))

(defun poor-cli--maybe-enable ()
  "Enable `poor-cli-mode' in buffers where it is appropriate."
  (unless (or (minibufferp)
              (derived-mode-p 'special-mode))
    (poor-cli-mode 1)))

(define-globalized-minor-mode global-poor-cli-mode
  poor-cli-mode poor-cli--maybe-enable)

(provide 'poor-cli)

;;; poor-cli.el ends here

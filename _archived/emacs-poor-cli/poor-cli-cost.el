;;; poor-cli-cost.el --- Cost tracking for poor-cli -*- lexical-binding: t; -*-

;;; Code:

(require 'subr-x)
(require 'poor-cli-rpc)
(require 'poor-cli-lists)

(defun poor-cli-get-session-cost-rpc (&optional params)
  "Return session cost."
  (poor-cli-request "poor-cli/getSessionCost" params))

(defun poor-cli-get-economy-savings-rpc (&optional params)
  "Return economy savings."
  (poor-cli-request "poor-cli/getEconomySavings" params))

(defun poor-cli-set-economy-preset-rpc (params)
  "Set economy preset with PARAMS."
  (poor-cli-request "poor-cli/setEconomyPreset" params))

(defun poor-cli-cost-show ()
  "Show current session cost."
  (interactive)
  (poor-cli-lists--show-detail
   "*poor-cli session cost*"
   (poor-cli-get-session-cost-rpc)))

(defun poor-cli-savings-show ()
  "Show economy savings."
  (interactive)
  (poor-cli-lists--show-detail
   "*poor-cli economy savings*"
   (poor-cli-get-economy-savings-rpc)))

(defun poor-cli-economy-preset ()
  "Set the economy preset."
  (interactive)
  (let ((preset (completing-read "Economy preset: " '("default" "economy" "performance") nil t)))
    (poor-cli-set-economy-preset-rpc (list :preset preset))
    (message "[poor-cli] Economy preset set to %s" preset)))

(provide 'poor-cli-cost)

;;; poor-cli-cost.el ends here

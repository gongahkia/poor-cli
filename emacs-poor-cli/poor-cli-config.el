;;; poor-cli-config.el --- Configuration management for poor-cli -*- lexical-binding: t; -*-

;;; Code:

(require 'subr-x)
(require 'transient)
(require 'poor-cli-rpc)
(require 'poor-cli-lists)

(defun poor-cli-list-config-options (&optional params)
  "Return config options."
  (poor-cli-request "poor-cli/listConfigOptions" params))

(defun poor-cli-get-config (params)
  "Get a config value with PARAMS."
  (poor-cli-request "poor-cli/getConfig" params))

(defun poor-cli-set-config-rpc (params)
  "Set a config value with PARAMS."
  (poor-cli-request "poor-cli/setConfig" params))

(defun poor-cli-toggle-config-rpc (params)
  "Toggle a config value with PARAMS."
  (poor-cli-request "poor-cli/toggleConfig" params))

(defun poor-cli-set-api-key-rpc (params)
  "Set an API key with PARAMS."
  (poor-cli-request "poor-cli/setApiKey" params))

(defun poor-cli-get-api-key-status-rpc (&optional params)
  "Return API key status."
  (poor-cli-request "poor-cli/getApiKeyStatus" params))

(defun poor-cli-config--entries ()
  "Return tabulated entries for config."
  (mapcar
   (lambda (opt)
     (list opt
           (vector
            (or (plist-get opt :key) "")
            (format "%s" (or (plist-get opt :value) ""))
            (or (plist-get opt :type) "")
            (or (plist-get opt :description) ""))))
   (poor-cli--normalize-seq (plist-get (poor-cli-list-config-options) :options))))

(defun poor-cli-config--edit ()
  "Edit the config option at point."
  (interactive)
  (when-let* ((opt (poor-cli-lists-current-payload))
              (key (plist-get opt :key)))
    (let ((value (read-string (format "%s: " key) (format "%s" (or (plist-get opt :value) "")))))
      (poor-cli-set-config-rpc (list :key key :value value))
      (poor-cli-lists-refresh))))

(defun poor-cli-config-toggle ()
  "Toggle the config option at point."
  (interactive)
  (when-let* ((opt (poor-cli-lists-current-payload))
              (key (plist-get opt :key)))
    (poor-cli-toggle-config-rpc (list :key key))
    (poor-cli-lists-refresh)))

(defun poor-cli-config-set ()
  "Set a config key-value pair."
  (interactive)
  (let ((key (read-string "Config key: "))
        (value (read-string "Config value: ")))
    (poor-cli-set-config-rpc (list :key key :value value))
    (message "[poor-cli] Config set")))

(defun poor-cli-set-api-key ()
  "Set an API key for a provider."
  (interactive)
  (let ((provider (completing-read "Provider: " '("gemini" "openai" "anthropic") nil t))
        (key (read-string "API key: ")))
    (poor-cli-set-api-key-rpc (list :provider provider :key key))
    (message "[poor-cli] API key set for %s" provider)))

(defun poor-cli-api-key-status ()
  "Show API key status."
  (interactive)
  (poor-cli-lists--show-detail
   "*poor-cli api-key-status*"
   (poor-cli-get-api-key-status-rpc)))

(defun poor-cli-config-open ()
  "Open the config list."
  (interactive)
  (poor-cli-lists--open
   poor-cli-config-buffer-name
   "config"
   [("Key" 24 t) ("Value" 24 t) ("Type" 12 t) ("Description" 0 t)]
   #'poor-cli-config--entries
   '(("RET" . poor-cli-config--edit)
     ("t" . poor-cli-config-toggle))))

(transient-define-prefix poor-cli-config-dispatch ()
  "Configuration command menu."
  [["Config"
    ("o" "Open list" poor-cli-config-open)
    ("s" "Set key" poor-cli-config-set)
    ("a" "API key status" poor-cli-api-key-status)
    ("k" "Set API key" poor-cli-set-api-key)]])

(provide 'poor-cli-config)

;;; poor-cli-config.el ends here

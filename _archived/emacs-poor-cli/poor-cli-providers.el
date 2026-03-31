;;; poor-cli-providers.el --- Provider management for poor-cli -*- lexical-binding: t; -*-

;;; Code:

(require 'subr-x)
(require 'poor-cli-rpc)
(require 'poor-cli-lists)

(defun poor-cli-list-providers-rpc (&optional params)
  "Return providers."
  (poor-cli-request "poor-cli/listProviders" params))

(defun poor-cli-get-provider-info-rpc (params)
  "Get provider info with PARAMS."
  (poor-cli-request "poor-cli/getProviderInfo" params))

(defun poor-cli-list-ollama-models-rpc (&optional params)
  "Return Ollama models."
  (poor-cli-request "poor-cli/listOllamaModels" params))

(defun poor-cli-providers--entries ()
  "Return tabulated entries for providers."
  (mapcar
   (lambda (provider)
     (list provider
           (vector
            (or (plist-get provider :name) "")
            (or (plist-get provider :status) "")
            (or (plist-get provider :model) "")
            (or (plist-get provider :capabilities) ""))))
   (poor-cli--normalize-seq (plist-get (poor-cli-list-providers-rpc) :providers))))

(defun poor-cli-provider-info ()
  "Show info for the provider at point."
  (interactive)
  (when-let* ((provider (poor-cli-lists-current-payload))
              (name (plist-get provider :name)))
    (poor-cli-lists--show-detail
     (format "*poor-cli provider %s*" name)
     (poor-cli-get-provider-info-rpc (list :name name)))))

(defun poor-cli-ollama-models ()
  "Show available Ollama models."
  (interactive)
  (poor-cli-lists--show-detail
   "*poor-cli Ollama models*"
   (poor-cli-list-ollama-models-rpc)))

(defun poor-cli-providers-open ()
  "Open the providers list."
  (interactive)
  (poor-cli-lists--open
   poor-cli-providers-buffer-name
   "providers"
   [("Name" 16 t) ("Status" 12 t) ("Model" 24 t) ("Capabilities" 0 t)]
   #'poor-cli-providers--entries
   '(("RET" . poor-cli-provider-info)
     ("o" . poor-cli-ollama-models))))

(provide 'poor-cli-providers)

;;; poor-cli-providers.el ends here

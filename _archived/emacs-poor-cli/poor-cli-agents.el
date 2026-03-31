;;; poor-cli-agents.el --- Agent management for poor-cli -*- lexical-binding: t; -*-

;;; Code:

(require 'subr-x)
(require 'poor-cli-rpc)
(require 'poor-cli-lists)

(defun poor-cli-create-agent-rpc (params)
  "Create an agent with PARAMS."
  (poor-cli-request "poor-cli/createAgent" params))

(defun poor-cli-list-agents (&optional params)
  "Return agents."
  (poor-cli-request "poor-cli/listAgents" params))

(defun poor-cli-get-agent (params)
  "Get an agent with PARAMS."
  (poor-cli-request "poor-cli/getAgent" params))

(defun poor-cli-start-agent-rpc (params)
  "Start an agent with PARAMS."
  (poor-cli-request "poor-cli/startAgent" params))

(defun poor-cli-cancel-agent-rpc (params)
  "Cancel an agent with PARAMS."
  (poor-cli-request "poor-cli/cancelAgent" params))

(defun poor-cli-get-agent-logs (params)
  "Get agent logs with PARAMS."
  (poor-cli-request "poor-cli/getAgentLogs" params))

(defun poor-cli-get-agent-result (params)
  "Get agent result with PARAMS."
  (poor-cli-request "poor-cli/getAgentResult" params))

(defun poor-cli-agents--entries ()
  "Return tabulated entries for agents."
  (mapcar
   (lambda (agent)
     (list agent
           (vector
            (or (plist-get agent :id) "")
            (or (plist-get agent :status) "")
            (truncate-string-to-width (or (plist-get agent :prompt) "") 30 nil nil t)
            (format "%s" (or (plist-get agent :cost) ""))
            (format "%s" (or (plist-get agent :runtime) "")))))
   (poor-cli--normalize-seq (plist-get (poor-cli-list-agents) :agents))))

(defun poor-cli-agent-create ()
  "Create a new agent."
  (interactive)
  (let ((prompt (read-string "Agent prompt: ")))
    (poor-cli-create-agent-rpc (list :prompt prompt))
    (message "[poor-cli] Agent created")))

(defun poor-cli-agent-start ()
  "Start the agent at point."
  (interactive)
  (when-let* ((agent (poor-cli-lists-current-payload))
              (id (plist-get agent :id)))
    (poor-cli-start-agent-rpc (list :id id))
    (poor-cli-lists-refresh)))

(defun poor-cli-agent-cancel ()
  "Cancel the agent at point."
  (interactive)
  (when-let* ((agent (poor-cli-lists-current-payload))
              (id (plist-get agent :id)))
    (poor-cli-cancel-agent-rpc (list :id id))
    (poor-cli-lists-refresh)))

(defun poor-cli-agent-logs ()
  "Show logs for the agent at point."
  (interactive)
  (when-let* ((agent (poor-cli-lists-current-payload))
              (id (plist-get agent :id)))
    (poor-cli-lists--show-detail
     (format "*poor-cli agent %s logs*" id)
     (poor-cli-get-agent-logs (list :id id)))))

(defun poor-cli-agent-result ()
  "Show result for the agent at point."
  (interactive)
  (when-let* ((agent (poor-cli-lists-current-payload))
              (id (plist-get agent :id)))
    (poor-cli-lists--show-detail
     (format "*poor-cli agent %s result*" id)
     (poor-cli-get-agent-result (list :id id)))))

(defun poor-cli-agents-open ()
  "Open the agent list."
  (interactive)
  (poor-cli-lists--open
   poor-cli-agents-buffer-name
   "agents"
   [("ID" 18 t) ("Status" 12 t) ("Prompt" 30 t) ("Cost" 10 t) ("Runtime" 10 t)]
   #'poor-cli-agents--entries
   '(("c" . poor-cli-agent-create)
     ("s" . poor-cli-agent-start)
     ("k" . poor-cli-agent-cancel)
     ("l" . poor-cli-agent-logs)
     ("r" . poor-cli-agent-result))))

(provide 'poor-cli-agents)

;;; poor-cli-agents.el ends here

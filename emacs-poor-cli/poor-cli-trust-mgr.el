;;; poor-cli-trust-mgr.el --- Trust management for poor-cli -*- lexical-binding: t; -*-

;;; Code:

(require 'subr-x)
(require 'transient)
(require 'poor-cli-rpc)
(require 'poor-cli-lists)

(defun poor-cli-get-trust-status-rpc (&optional params)
  "Return trust status."
  (poor-cli-request "poor-cli/getTrustStatus" params))

(defun poor-cli-trust-repo-rpc (params)
  "Trust a repo with PARAMS."
  (poor-cli-request "poor-cli/trustRepo" params))

(defun poor-cli-untrust-repo-rpc (params)
  "Untrust a repo with PARAMS."
  (poor-cli-request "poor-cli/untrustRepo" params))

(defun poor-cli-list-profiles (&optional params)
  "Return trust profiles."
  (poor-cli-request "poor-cli/listProfiles" params))

(defun poor-cli-apply-profile-rpc (params)
  "Apply a trust profile with PARAMS."
  (poor-cli-request "poor-cli/applyProfile" params))

(defun poor-cli-trust-status ()
  "Show trust status."
  (interactive)
  (poor-cli-lists--show-detail
   "*poor-cli trust status*"
   (poor-cli-get-trust-status-rpc)))

(defun poor-cli-trust-repo ()
  "Trust a repository path."
  (interactive)
  (let ((path (read-string "Repo path: " default-directory)))
    (poor-cli-trust-repo-rpc (list :path path))
    (message "[poor-cli] Repo trusted")))

(defun poor-cli-untrust-repo ()
  "Untrust a repository path."
  (interactive)
  (let ((path (read-string "Repo path: " default-directory)))
    (poor-cli-untrust-repo-rpc (list :path path))
    (message "[poor-cli] Repo untrusted")))

(defun poor-cli-profiles--entries ()
  "Return tabulated entries for trust profiles."
  (mapcar
   (lambda (profile)
     (list profile
           (vector
            (or (plist-get profile :name) "")
            (or (plist-get profile :description) ""))))
   (poor-cli--normalize-seq (plist-get (poor-cli-list-profiles) :profiles))))

(defun poor-cli-profile-apply ()
  "Apply the trust profile at point."
  (interactive)
  (when-let* ((profile (poor-cli-lists-current-payload))
              (name (plist-get profile :name)))
    (poor-cli-apply-profile-rpc (list :name name))
    (message "[poor-cli] Profile %s applied" name)))

(defun poor-cli-profiles-open ()
  "Open the trust profiles list."
  (interactive)
  (poor-cli-lists--open
   poor-cli-profiles-buffer-name
   "profiles"
   [("Name" 24 t) ("Description" 0 t)]
   #'poor-cli-profiles--entries
   '(("RET" . poor-cli-profile-apply))))

(transient-define-prefix poor-cli-trust-dispatch ()
  "Trust management command menu."
  [["Trust"
    ("s" "Status" poor-cli-trust-status)
    ("t" "Trust repo" poor-cli-trust-repo)
    ("u" "Untrust repo" poor-cli-untrust-repo)]
   ["Profiles"
    ("p" "Profiles list" poor-cli-profiles-open)
    ("a" "Apply profile" poor-cli-profile-apply)]])

(provide 'poor-cli-trust-mgr)

;;; poor-cli-trust-mgr.el ends here

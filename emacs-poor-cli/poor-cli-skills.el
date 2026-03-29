;;; poor-cli-skills.el --- Skill browser for poor-cli -*- lexical-binding: t; -*-

;;; Code:

(require 'subr-x)
(require 'poor-cli-rpc)
(require 'poor-cli-lists)

(defun poor-cli-list-skills (&optional params)
  "Return skills."
  (poor-cli-request "poor-cli/listSkills" params))

(defun poor-cli-get-skill (params)
  "Get a skill with PARAMS."
  (poor-cli-request "poor-cli/getSkill" params))

(defun poor-cli-skills--entries ()
  "Return tabulated entries for skills."
  (mapcar
   (lambda (skill)
     (list skill
           (vector
            (or (plist-get skill :name) "")
            (or (plist-get skill :description) "")
            (or (plist-get skill :scope) ""))))
   (poor-cli--normalize-seq (plist-get (poor-cli-list-skills) :skills))))

(defun poor-cli-skill-show ()
  "Show the skill at point."
  (interactive)
  (when-let* ((skill (poor-cli-lists-current-payload))
              (name (plist-get skill :name)))
    (poor-cli-lists--show-detail
     (format "*poor-cli skill %s*" name)
     (poor-cli-get-skill (list :name name)))))

(defun poor-cli-skills-open ()
  "Open the skills list."
  (interactive)
  (poor-cli-lists--open
   poor-cli-skills-buffer-name
   "skills"
   [("Name" 20 t) ("Description" 40 t) ("Scope" 12 t)]
   #'poor-cli-skills--entries
   '(("RET" . poor-cli-skill-show))))

(provide 'poor-cli-skills)

;;; poor-cli-skills.el ends here

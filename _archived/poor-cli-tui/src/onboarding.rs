pub struct OnboardingStep {
    pub title: &'static str,
    pub objective: &'static str,
    pub commands: &'static [&'static str],
    pub try_now: &'static str,
}

pub const ONBOARDING_STEPS: &[OnboardingStep] = &[
    OnboardingStep {
        title: "Get Oriented",
        objective:
            "Start with visibility into your session and where to find command docs quickly.",
        commands: &[
            "/help",
            "/status",
            "/bootstrap",
            "/profile status",
            "/search <term>",
        ],
        try_now: "/bootstrap",
    },
    OnboardingStep {
        title: "Safety Net",
        objective: "poor-cli auto-saves checkpoints before every file change. Use /undo to revert and /checkpoints to browse history.",
        commands: &["/undo", "/checkpoint [name]", "/checkpoints"],
        try_now: "/checkpoints",
    },
    OnboardingStep {
        title: "Choose Provider + Model",
        objective: "Configure API keys with /setup, then inspect or switch providers with /provider. Press F2 for quick access.",
        commands: &["/setup", "/provider", "/provider switch", "/api-key status"],
        try_now: "/setup",
    },
    OnboardingStep {
        title: "Run Local Services",
        objective: "Control local dependencies from the TUI instead of shelling out.",
        commands: &[
            "/service status",
            "/service start <name> <command...>",
            "/service logs <name> [lines]",
            "/ollama start",
        ],
        try_now: "/service status",
    },
    OnboardingStep {
        title: "Run Collaboration Sessions",
        objective: "Start a mob or review room, invite collaborators, and keep the session moving with handoff and agenda commands.",
        commands: &[
            "/collab start mob",
            "/collab join <invite-code>",
            "/collab members",
            "/collab handoff next",
            "/collab agenda add <text>",
        ],
        try_now: "/collab start mob",
    },
    OnboardingStep {
        title: "Daily Coding Workflow",
        objective: "Use these commands for context, review, and tests.",
        commands: &[
            "/add <path>",
            "/files",
            "/review [file]",
            "/test <file>",
        ],
        try_now: "/files",
    },
];

pub fn onboarding_step_count() -> usize {
    ONBOARDING_STEPS.len()
}

pub struct OwlExpression {
    pub lines: &'static [&'static str],
    pub speech: &'static str,
}

pub const OWL_EXPRESSIONS: &[OwlExpression] = &[
    OwlExpression { // step 1: waving
        lines: &["  {o,o}/", "  /)__)  ", "  -\"-\"- "],
        speech: "Hey! Let me show you around.",
    },
    OwlExpression { // step 2: neutral
        lines: &["  {o,o} ", "  /)__) ", "  -\"-\"- "],
        speech: "Safety first! I've got your back.",
    },
    OwlExpression { // step 3: thinking
        lines: &["  {o,o}?", "  /)__)  ", "  -\"-\"- "],
        speech: "Time to pick a brain... er, provider!",
    },
    OwlExpression { // step 4: pointing
        lines: &["  {o,o}>", "  /)__)> ", "  -\"-\"-  "],
        speech: "Let's get the engines running!",
    },
    OwlExpression { // step 5: social
        lines: &[" <{o,o}>", "  /)__)  ", "  -\"-\"-  "],
        speech: "Teamwork makes the dream work!",
    },
    OwlExpression { // step 6: celebrating
        lines: &[" \\{^,^}/", "  /)__)  ", "  -\"-\"-  "],
        speech: "You're all set! Go build something!",
    },
];

pub fn owl_for_step(step: usize) -> &'static OwlExpression {
    OWL_EXPRESSIONS.get(step).unwrap_or(&OWL_EXPRESSIONS[0])
}

pub fn owl_message(expression_idx: usize, text: &str) -> String {
    let owl = owl_for_step(expression_idx);
    format!("{}\n{}\n{}\n\n{}", owl.lines[0], owl.lines[1], owl.lines[2], text)
}

pub fn onboarding_navigation_hint() -> &'static str {
    "Navigation: `/onboarding next` \u{2022} `/onboarding prev` \u{2022} `/onboarding <step>` \u{2022} `/onboarding exit`"
}

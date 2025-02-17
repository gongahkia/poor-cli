concrete Wfh of Zoom = {

    lincat

        Task,
        TechIssue,
        Distraction,
        Excuse,
        Colleague,
        ZoomCall = Str;

    lin

        WifiIssues = "my Wifi is cutting out";
        MicNotWorking = "my mic isn't working";
        CameraOff = "my camera is off for some reason";
        Lagging = "i'm lagging pretty badly";
        SoundCuttingOut = "the sound is cutting out";
        FrozenScreen = "my screen is frozen";

        DogBarking = "my dog is barking";
        KidsScreaming = "the kids are screaming";
        Doorbell = "someone's at the door";
        ConstructionNoise = "there's construction going on";
        TypingTooLoud = "my typing is too loud";
        TVInBackground = "there's TV noise in the background";
        EatingSnack = "i'm eating something quickly";
        SpouseInterrupting = "my spouse is interrupting";

        Presentation = "giving a presentation";
        Feedback = "providing feedback";
        BrainstormingSession = "in a brainstorming session";
        CheckIn = "doing a check-in";
        Report = "discussing the report";
        TeamMeeting = "in the team meeting";

        Boss = "with my boss";
        TeamLead = "team lead is here";
        Client = "client's on the call";
        CoWorker = "talking to a coworker";

        SorryAboutTheNoise = "sorry about the noise";
        OneSecLetMeFixThat = "one sec, let me fix that";
        CanYouRepeatThat = "can you repeat that?";
        MyConnectionIsBad = "my connection is bad";
        LetMeMuteForASecond = "let me mute for a second";
        I’llBeRightBack = "i'll be right back";
        IThinkYou’reMuted = "i think you're muted";
        I’mHavingSomeIssuesHere = "i'm having some issues here";

        ----

        ZoomRoutine teamMeeting WifiIssues dogBarking sorryAboutTheNoise boss = "in the team meeting, my Wifi is cutting out, my dog is barking, sorry about the noise, with my boss";
}
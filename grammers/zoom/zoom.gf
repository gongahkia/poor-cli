abstract Zoom = {

   flags startCategory = ZoomCall ;

   cat

      Excuse;
      Distraction;
      Task;
      Colleague;
      TechIssue;

   fun

      WifiIssues, MicNotWorking, CameraOff, Lagging, SoundCuttingOut, FrozenScreen : TechIssue;
      DogBarking, KidsScreaming, Doorbell, ConstructionNoise, TypingTooLoud, TVInBackground, EatingSnack, SpouseInterrupting : Distraction;
      Presentation, Feedback, BrainstormingSession, CheckIn, Report, TeamMeeting : Task;
      Boss, TeamLead, Client, CoWorker : Colleague;
      SorryAboutTheNoise, OneSecLetMeFixThat, CanYouRepeatThat, MyConnectionIsBad, LetMeMuteForASecond, I’llBeRightBack, IThinkYou’reMuted, I’mHavingSomeIssuesHere : Excuse;

      ----

      ZoomRoutine : Task -> TechIssue -> Distraction -> Excuse -> Colleague -> ZoomCall;

}
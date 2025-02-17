abstract Singlish = {

   flags startCategory = Phrase ;

   cat

      BasePhrase;
      Emphasis;
      AddOns;
      Phrase;

   fun

      Lah, Lor, Meh, Leh, Sia, Ah, Ho, Wah, Eh, Oi, Boh, Liao, Huat, Shiok, WaLauEh : BasePhrase;
      DefaultEmphasis, Very, Super, Sumpa, Confirm, Damn, Shiok, DieDie, Sibeh : Emphasis;
      DefaultAddOns, Already, Only, IsIt, One, Can, SureAnot, Cannot, What, LikeThat, Right, ThenHow : AddOns;

      ----

      Speak : BasePhrase -> Emphasis -> AddOns -> Phrase;

}

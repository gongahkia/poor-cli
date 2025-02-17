abstract SmallTalk = {

   flags startCategory = Talk ;

   cat

      Greeting;
      Weather;
      Compliment;
      Topic;
      Response;

   fun

      Hi, Hello, Hey, GoodMorning, GoodAfternoon, GoodEvening : Greeting;
      Sunny, Rainy, Cloudy, Snowy, Hot, Cold, Windy, Humid, NiceDay, BeautifulWeather : Weather;
      YouLookGreat, NiceOutfit, CoolShoes, NiceHaircut, LoveYourStyle : Compliment;
      Work, WeekendPlans, Family, Hobbies, Travel, Movies, TVShows, Sports : Topic;
      OhReally, ThatSoundsGreat, Interesting, TellMeMore, Wow, Cool, SoundsFun : Response;

      ----

      SmallTalk : Greeting -> Weather -> Compliment -> Topic -> Response -> Talk;

}
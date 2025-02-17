abstract CaiFan = {

   flags startCategory = Meal ;

   cat

      Carb;
      Protein;
      Vegetable;
      Gravy;
      Spiciness;
      AddOns;
      Location;
      Meal;

   fun

      DefaultRice, NoRice, WhiteRice, BrownRice, FriedRice, FriedNoodles : Carb;
      Cereal, Thai, BlackPepper, Mapo : ProteinFlavour;
      Chicken, Fish, Pork, Tofu : Protein;
      Cabbage, Spinach, Eggplant, Beansprouts, Longbean : Vegetable;
      DefaultGravy, MoreGravy, LessGravy, NoGravy : Gravy;
      DefaultSpiciness, Spicy, NotSpicy : Spiciness;
      DefaultAddOns, FriedEgg, SteamedEgg, SunnySideUpEgg, TofuCubes, Otah : AddOns;
      DefaultLocation, HavingHere, TakeAway : Location;

      ----

      GeiWo : Carb -> ProteinFlavour -> Protein -> Vegetable -> Gravy -> Spiciness -> AddOns -> Location -> Meal;

}

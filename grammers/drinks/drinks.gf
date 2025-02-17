abstract Drinks = {

   flags startCategory = Drink ;

   cat

      BaseDrink;
      Drink;
      Milk;
      Thickness;
      Sweetness;
      AddOns;
      Temperature;
      Location;

   fun

      Kopi, Teh , Milo, KopiAndTea : BaseDrink;
      Condensed, Evaporated, NoMilk : Milk;
      DefaultThickness, Thin, Thick, AllTheWay : Thickness;
      DefaultAddOns, Butter, WithMilo, Pulled : AddOns;
      DefaultSweetness, MoreSugar, LessSugar, NoSugar : Sweetness;
      DefaultTemperature, Hot, Warm, Ice : Temperature;
      DefaultLocation, HavingHere, TakeAway : Location;

      ----

      Order : BaseDrink -> Milk -> Thickness -> AddOns -> Sweetness -> Temperature -> Location -> Drink;

}

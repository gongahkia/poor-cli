concrete Kopi of Drinks = {

    lincat

        BaseDrink,
        Drink,
        Milk,
        Thickness,
        Sweetness,
        AddOns;
        Temperature,
        Location = Str;

    lin

        Kopi = "kopi";
        Teh = "teh";
        Milo = "milo";
        KopiAndTea = "yuan yang";

        Condensed = "";
        Evaporated = "c";
        NoMilk = "o";

        DefaultThickness = Thick;
        Thin = "po" ;
        Thick = "gao" ;
        AllTheWay = "dilo" ;

        DefaultAddOns = "";
        Butter = "gu you";
        WithMilo = "cino";
        Pulled = "tarik";

        DefaultSweetness = "";
        MoreSugar = "ga dai";
        LessSugar = "siew dai";
        NoSugar = "kosong";

        DefaultTemperature = Ice;
        Hot = "siu";
        Warm = "bua siu";
        Ice = "beng";

        DefaultLocation = HavingHere;
        HavingHere = "he de";
        TakeAway = "dabao";

        ----

        Order kopi c gao kosong beng dabao = kopi ++ c ++ gao ++ kosong ++ beng ++ dabao;

}

concrete Parklane of CaiFan = {

     lincat

        Carb,
        Protein,
        Vegetable,
        Gravy,
        Spiciness,
        AddOns,
        Location,
        Meal = Str;

    lin

        DefaultRice = NoRice;
        NoRice = "bu yao fan";
        WhiteRice = "bai fan";
        BrownRice = "cao mi fan";
        FriedRice = "chao fan";
        FriedNoodles = "chao mian";

        Cereal = "mai pian";
        Thai = "tai shi";
        BlackPepper = "zhe ge";
        Mapo = "mapo";

        Chicken = "ji rou";
        Fish = "yu pian";
        Pork = "zhu rou";

        Cabbage = "bai cai";
        Spinach = "bo cai";
        Eggplant = "qie zi";
        Beansprouts = "dou ya";
        Longbean = "chang dou";

        DefaultGravy = NoGravy;
        MoreGravy = "ling zhi duo yi dian";
        LessGravy = "ling zhi shao yi dian";
        NoGravy = "bu yao ling zhi";

        DefaultSpiciness = Spicy;
        Spicy = "la jiao";
        NotSpicy = "bu yao la";

        DefaultAddOns = "";
        FriedEgg = "chao dan";
        SteamedEgg = "shui dan";
        SunnySideUpEgg = "he bao dan";
        TofuCubes = "dou fu kuai";
        Otah = "otah";

        DefaultLocation = HavingHere;
        HavingHere = "chi de";
        TakeAway = "da bao";

        ----

        GeiWo bai fan mai pian ji rou bai cai jia tang bu yao la chao dan da bao = bai fan ++ mai pian ++ ji rou ++ bai cai ++ jia tang ++ bu yao la ++ chao dan ++ da bao;

}

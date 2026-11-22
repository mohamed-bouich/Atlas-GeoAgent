"""Labelled questions for the parsing benchmark: 38 cases, English and French.

kind = "complete"  : everything is given, the parser must extract every field.
kind = "missing"   : something is missing, the agent must ASK instead of guessing.
kind = "invalid"   : everything is given but a rule is broken (old year, huge zone, same year, future).
hard = True        : a complete question phrased freely (lowercase, no preposition, mixed languages, a number
                     written in words...). A regex parser is expected to struggle here, which is the point.
`problems` is what agent.planner.find_problems must return for that question.
Places are written exactly as in the question: the parser must not translate or correct them.
"""


def case(question, lang, kind="complete", place=None, season=None, years=None, index="ndvi",
         distance=None, dist_kind=None, problems=(), hard=False):
    return {
        "question": question, "lang": lang, "kind": kind, "hard": hard,
        "expected": {"place": place, "season": season, "years": years, "index": index,
                     "distance_km": distance, "distance_kind": dist_kind},
        "problems": list(problems),
    }


QUESTIONS = [
    # ---------------- English, complete ----------------
    case("How did vegetation change around Al Hoceima between summer 2023 and summer 2024?", "en",
         place="Al Hoceima", season="summer", years=(2023, 2024)),
    case("Did vegetation around Agadir change between winter 2022 and winter 2025?", "en",
         place="Agadir", season="winter", years=(2022, 2025)),
    case("Compare the greenness of Rabat in spring 2021 and spring 2024.", "en",
         place="Rabat", season="spring", years=(2021, 2024)),
    case("How much forest burned near Chefchaouen between summer 2021 and summer 2023?", "en",
         place="Chefchaouen", season="summer", years=(2021, 2023), index="nbr"),
    case("Has the water level of the lake near Ouarzazate changed between autumn 2022 and autumn 2024?", "en",
         place="Ouarzazate", season="autumn", years=(2022, 2024), index="ndwi"),
    case("What happened to vegetation in Tetouan from summer 2022 to summer 2025?", "en",
         place="Tetouan", season="summer", years=(2022, 2025)),
    case("Vegetation change in Marrakech, summer 2020 versus summer 2024.", "en",
         place="Marrakech", season="summer", years=(2020, 2024)),
    case("How did vegetation change within 3 km of Al Hoceima between summer 2023 and summer 2024?", "en",
         place="Al Hoceima", season="summer", years=(2023, 2024), distance=3, dist_kind="radius"),
    case("Analyse a 5 km zone around Nador, spring 2023 vs spring 2024.", "en",
         place="Nador", season="spring", years=(2023, 2024), distance=5, dist_kind="width"),
    case("Is Dakhla greener in autumn 2024 than in autumn 2022?", "en",
         place="Dakhla", season="autumn", years=(2022, 2024)),
    case("Wildfire damage near Oujda, summer 2022 compared to summer 2024.", "en",
         place="Oujda", season="summer", years=(2022, 2024), index="nbr"),
    case("Did the lakes around Ifrane gain water between spring 2023 and spring 2025?", "en",
         place="Ifrane", season="spring", years=(2023, 2025), index="ndwi"),
    case("How did the greenness around Essaouira change between summer 2022 and summer 2024, within 2 km?", "en",
         place="Essaouira", season="summer", years=(2022, 2024), distance=2, dist_kind="radius"),
    case("Compare vegetation in Fes in winter 2023 and winter 2024.", "en",
         place="Fes", season="winter", years=(2023, 2024)),
    # ---------------- French, complete ----------------
    case("Comment la végétation a-t-elle évolué autour d'Al Hoceima entre l'été 2023 et l'été 2024 ?", "fr",
         place="Al Hoceima", season="summer", years=(2023, 2024)),
    case("La végétation autour de Tanger a-t-elle changé entre l'hiver 2022 et l'hiver 2024 ?", "fr",
         place="Tanger", season="winter", years=(2022, 2024)),
    case("Quelle est l'évolution de la verdure à Casablanca entre le printemps 2021 et le printemps 2024 ?", "fr",
         place="Casablanca", season="spring", years=(2021, 2024)),
    case("Quelle surface a brûlé près de Chefchaouen entre l'été 2021 et l'été 2023 ?", "fr",
         place="Chefchaouen", season="summer", years=(2021, 2023), index="nbr"),
    case("Le niveau d'eau du lac près d'Ifrane a-t-il changé entre l'automne 2022 et l'automne 2024 ?", "fr",
         place="Ifrane", season="autumn", years=(2022, 2024), index="ndwi"),
    case("Dans un rayon de 3 km autour d'Agadir, comment la végétation a-t-elle changé entre l'été 2023 et l'été 2024 ?", "fr",
         place="Agadir", season="summer", years=(2023, 2024), distance=3, dist_kind="radius"),
    case("Analyse une zone de 5 km autour de Nador, printemps 2023 contre printemps 2024.", "fr",
         place="Nador", season="spring", years=(2023, 2024), distance=5, dist_kind="width"),
    case("Évolution de la végétation à Marrakech, été 2020 et été 2024.", "fr",
         place="Marrakech", season="summer", years=(2020, 2024)),
    case("Y a-t-il eu un incendie autour d'Oujda entre l'été 2022 et l'été 2024 ?", "fr",
         place="Oujda", season="summer", years=(2022, 2024), index="nbr"),
    case("Compare la végétation de Fès en automne 2022 et en automne 2025.", "fr",
         place="Fès", season="autumn", years=(2022, 2025)),
    case("Comment la végétation a-t-elle changé à Rabat entre l'hiver 2023 et l'hiver 2025 ?", "fr",
         place="Rabat", season="winter", years=(2023, 2025)),
    case("Dans un rayon de 2,5 km autour de Tétouan, évolution de la végétation entre l'été 2022 et l'été 2024.", "fr",
         place="Tétouan", season="summer", years=(2022, 2024), distance=2.5, dist_kind="radius"),
    # ---------------- missing information: the agent must ask ----------------
    case("How did vegetation change in Rabat?", "en", "missing", place="Rabat", problems=("season", "years")),
    case("How did vegetation change in Agadir in summer?", "en", "missing", place="Agadir", season="summer", problems=("years",)),
    case("Compare Tangier between 2022 and 2024.", "en", "missing", place="Tangier", years=(2022, 2024), problems=("season",)),
    case("What changed between summer 2023 and summer 2024?", "en", "missing", season="summer", years=(2023, 2024), problems=("place",)),
    case("Comment la végétation a-t-elle évolué à Tanger ?", "fr", "missing", place="Tanger", problems=("season", "years")),
    case("Compare Rabat last summer and this summer.", "en", "missing", place="Rabat", season="summer", problems=("years",)),
    case("Y a-t-il eu des changements autour d'Al Hoceima entre 2022 et 2024 ?", "fr", "missing",
         place="Al Hoceima", years=(2022, 2024), problems=("season",)),
    case("Vegetation change in summer 2023 vs summer 2024.", "en", "missing", season="summer", years=(2023, 2024), problems=("place",)),
    # ---------------- invalid: a rule is broken ----------------
    case("How did vegetation change around Al Hoceima between summer 2015 and summer 2024?", "en", "invalid",
         place="Al Hoceima", season="summer", years=(2015, 2024), problems=("old_year",)),
    case("How did vegetation change within 40 km of Agadir between summer 2023 and summer 2024?", "en", "invalid",
         place="Agadir", season="summer", years=(2023, 2024), distance=40, dist_kind="radius", problems=("size",)),
    case("Compare Rabat in summer 2024 and summer 2024.", "en", "invalid",
         place="Rabat", season="summer", years=(2024, 2024), problems=("same_year",)),
    case("How did vegetation change around Agadir between summer 2025 and summer 2030?", "en", "invalid",
         place="Agadir", season="summer", years=(2025, 2030), problems=("future",)),
    # ---------------- hard: free phrasing, complete information ----------------
    case("how did vegetation change around al hoceima between summer 2023 and summer 2024", "en",
         place="Al Hoceima", season="summer", years=(2023, 2024), hard=True),
    case("I live in Nador and I would like to know whether the hills around town lost their trees from summer 2022 to summer 2024.", "en",
         place="Nador", season="summer", years=(2022, 2024), hard=True),
    case("Rabat: vegetation change, summer 2021 vs summer 2023.", "en",
         place="Rabat", season="summer", years=(2021, 2023), hard=True),
    case("Comment la végétation a changé autour de Rabat between summer 2022 and summer 2024?", "fr",
         place="Rabat", season="summer", years=(2022, 2024), hard=True),
    case("comment la végétation a évolué à tanger entre l'été 2022 et l'été 2024", "fr",
         place="Tanger", season="summer", years=(2022, 2024), hard=True),
    case("Marrakech vegetation, summer 2020 vs 2024.", "en",
         place="Marrakech", season="summer", years=(2020, 2024), hard=True),
    case("Analyse within three km of Agadir, summer 2023 vs summer 2024.", "en",
         place="Agadir", season="summer", years=(2023, 2024), distance=3, dist_kind="radius", hard=True),
    case("Did a big fire destroy the forest on the hills near Larache between summer 2021 and summer 2022?", "en",
         place="Larache", season="summer", years=(2021, 2022), index="nbr", hard=True),
    case("The water in the reservoir by Taounate: more or less between spring 2023 and spring 2025?", "en",
         place="Taounate", season="spring", years=(2023, 2025), index="ndwi", hard=True),
]

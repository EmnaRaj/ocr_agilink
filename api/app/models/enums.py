import enum


class StatutFiche(str, enum.Enum):
    extrait = "extrait"
    en_revue = "en_revue"
    valide = "valide"


class Partie(str, enum.Enum):
    p1 = "1"
    p2 = "2"
    controle = "controle"


class StatutRevue(str, enum.Enum):
    auto = "auto"  # accepted automatically, above confidence threshold
    a_revoir = "a_revoir"  # flagged for human review
    corrige = "corrige"  # corrected by a human


class TypeControle(str, enum.Enum):
    controle_electrique = "controle_electrique"
    controle_final = "controle_final"
    correspondance_serie = "correspondance_serie"


class Methode(str, enum.Enum):
    manuel = "manuel"
    banc_de_test = "banc_de_test"

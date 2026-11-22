"""Cache basé sur des fichiers pour les résultats coûteux des outils.

Pourquoi utiliser notre propre cache plutôt que celui de Prefect :
l'application Streamlit et l'agent ont ensuite besoin d'accéder aux
fichiers réels (cartes, tableaux) dans data/cache/, et pas uniquement
à une valeur de retour stockée dans le répertoire interne de Prefect.
"""


import hashlib
import json
import numpy as np
from affine import Affine
import config
from tools.change import ChangeResult,ChangeSummary

def make_key(tool:str,**params)->str:
    """Génère une clé déterministe : mêmes entrées = même clé, quel que soit l'ordre des arguments."""
    payload=json.dumps({"tool":tool,**params},sort_keys=True,default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]
def save_change(key:str,result:ChangeResult)->None:
    folder=config.CACHE_DIR/key
    folder.mkdir(parents=True,exist_ok=True)
    # NumPy stocke les tableaux de résultats dans un format compressé.
    np.savez_compressed(folder/"delta.npz",delta=result.delta,classes=result.classes)
    # Les métadonnées spatiales sont séparées des données raster.
    (folder/"meta.json").write_text(json.dumps({"transform":list(result.transform)[:6],"crs":result.crs}))

    # Ce fichier est écrit en dernier : sa présence indique que le cache
    # est complet et évite de charger une entrée partiellement écrite.
    (folder/"summary.json").write_text(result.summary.model_dump_json(indent=2))

def load_change(key:str)->ChangeResult|None:
    folder=config.CACHE_DIR/key
    summary_path=folder/"summary.json"
    if not summary_path.exists():
        return None
    try:
    # Chargement des tableaux NumPy et reconstruction des métadonnées
    # nécessaires pour conserver la référence spatiale du résultat.
        with np.load(folder/"delta.npz")as data:
            delta,classes=data["delta"],data["classes"]
            meta=json.loads((folder/"meta.json").read_text())
            return ChangeResult(delta=delta
                                ,classes=classes,
                                transform=Affine(*meta["transform"]),
                                crs=meta["crs"],
                                summary=ChangeSummary.model_validate_json(summary_path.read_text()))
    except(OSError,ValueError,KeyError):
        # Une entrée corrompue est considérée comme un cache manquant.
        return None    # a corrupt entry is just a cache miss

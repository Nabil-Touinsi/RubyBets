# Rôle du fichier :
# Ce script télécharge les datasets historiques Premier League depuis Football-Data.co.uk
# et les range dans data/ml/raw/premier_league pour préparer l'entraînement ML.

from pathlib import Path
import urllib.request


PROJECT_ROOT = Path(__file__).resolve().parents[3]
OUTPUT_DIR = PROJECT_ROOT / "data" / "ml" / "raw" / "premier_league"

LEAGUE_CODE = "E0"
BASE_URL = "https://www.football-data.co.uk/mmz4281"


# Génère les saisons manquantes de 2000/2001 à 2017/2018.
def build_missing_seasons() -> list[tuple[str, str]]:
    seasons = []

    for start_year in range(2000, 2018):
        end_year = start_year + 1

        short_code = f"{str(start_year)[-2:]}{str(end_year)[-2:]}"
        file_name = f"{LEAGUE_CODE}_{start_year}_{end_year}.csv"

        seasons.append((short_code, file_name))

    return seasons


# Télécharge un fichier CSV s'il n'existe pas déjà localement.
def download_dataset(short_code: str, file_name: str) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    output_path = OUTPUT_DIR / file_name
    url = f"{BASE_URL}/{short_code}/{LEAGUE_CODE}.csv"

    if output_path.exists():
        print(f"Déjà présent : {file_name}")
        return

    print(f"Téléchargement : {file_name}")
    print(f"Source : {url}")

    urllib.request.urlretrieve(url, output_path)

    print(f"OK : {output_path}")


# Lance le téléchargement de toutes les saisons manquantes.
def main() -> None:
    seasons = build_missing_seasons()

    for short_code, file_name in seasons:
        download_dataset(short_code, file_name)

    print("Téléchargement des saisons manquantes terminé.")


if __name__ == "__main__":
    main()


# Schéma de communication :
# Football-Data.co.uk
#        ↓
# backend/scripts/ml/download_premier_league_datasets.py
#        ↓
# data/ml/raw/premier_league/*.cs
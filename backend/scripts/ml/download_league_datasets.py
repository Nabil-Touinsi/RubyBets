# Ce fichier télécharge les datasets historiques Football-Data.co.uk pour les ligues RubyBets compatibles.

import argparse
from pathlib import Path
from urllib.request import urlretrieve


LEAGUES = {
    "ligue_1": {
        "code": "F1",
        "folder": "data/ml/raw/ligue_1",
    },
    "bundesliga": {
        "code": "D1",
        "folder": "data/ml/raw/bundesliga",
    },
    "serie_a": {
        "code": "I1",
        "folder": "data/ml/raw/serie_a",
    },
    "la_liga": {
        "code": "SP1",
        "folder": "data/ml/raw/la_liga",
    },
}


# Transforme une saison RubyBets 2023_2024 en format Football-Data 2324.
def build_football_data_season_code(start_year: int) -> str:
    end_year = start_year + 1
    return f"{str(start_year)[-2:]}{str(end_year)[-2:]}"


# Télécharge un fichier CSV si celui-ci n'existe pas déjà localement.
def download_dataset(league_name: str, league_config: dict, start_year: int) -> None:
    season_code = build_football_data_season_code(start_year)
    season_label = f"{start_year}_{start_year + 1}"

    league_code = league_config["code"]
    target_folder = Path(league_config["folder"])
    target_folder.mkdir(parents=True, exist_ok=True)

    target_file = target_folder / f"{league_code}_{season_label}.csv"
    source_url = f"https://www.football-data.co.uk/mmz4281/{season_code}/{league_code}.csv"

    if target_file.exists():
        print(f"SKIP {league_name} {season_label} déjà présent")
        return

    print(f"DOWNLOAD {league_name} {season_label}")
    urlretrieve(source_url, target_file)
    print(f"OK {target_file}")


# Récupère les paramètres de téléchargement demandés dans le terminal.
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Télécharge les datasets historiques Football-Data.co.uk."
    )

    parser.add_argument(
        "--league",
        choices=LEAGUES.keys(),
        help="Nom de la ligue à télécharger. Si absent, toutes les ligues sont traitées.",
    )

    parser.add_argument(
        "--start-year",
        type=int,
        default=2000,
        help="Première saison à télécharger, ex: 2000 pour 2000_2001.",
    )

    parser.add_argument(
        "--end-year",
        type=int,
        default=2024,
        help="Dernière saison à télécharger, ex: 2024 pour 2024_2025.",
    )

    return parser.parse_args()


# Lance le téléchargement selon les paramètres fournis.
def main() -> None:
    args = parse_args()

    selected_leagues = (
        {args.league: LEAGUES[args.league]}
        if args.league
        else LEAGUES
    )

    for league_name, league_config in selected_leagues.items():
        for start_year in range(args.start_year, args.end_year + 1):
            try:
                download_dataset(league_name, league_config, start_year)
            except Exception as error:
                print(f"ERREUR {league_name} {start_year}_{start_year + 1} : {error}")


if __name__ == "__main__":
    main()


# Schéma de communication :
# Football-Data.co.uk
#        ↓
# backend/scripts/ml/download_league_datasets.py
#        ↓
# data/ml/raw/ligue_1/*.csv
# data/ml/raw/bundesliga/*.csv
# data/ml/raw/serie_a/*.csv
# data/ml/raw/la_liga/*.csv
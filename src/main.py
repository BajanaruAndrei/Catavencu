import os
import sys
import io
import yaml
import logging
from dotenv import load_dotenv

# Forțăm UTF-8 pentru terminal pe Windows și console redirection (rezolvă bug-ul 1 de encoding)
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    except Exception:
        pass
if sys.stderr.encoding != 'utf-8':
    try:
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    except Exception:
        pass

# Adăugăm directorul 'src' în sys.path pentru a garanta funcționarea importurilor locale
director_curent = os.path.dirname(os.path.abspath(__file__))
if director_curent not in sys.path:
    sys.path.append(director_curent)

from fetcher import descarca_si_filtreaza_stiri
from summarizer import proceseaza_si_rezuma_stiri
from telegram_sender import trimite_digest_telegram
from site_builder import actualizeaza_arhiva, construieste_site

# Configurare logging cu forțare codare UTF-8 (rezolvă bug-ul 1 de encoding)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    encoding="utf-8"
)

def main():
    logging.info("=== Pornire Orchestrator TechDigest ===")
    
    director_proiect = os.path.dirname(director_curent)
    
    # Încărcăm variabilele de mediu din fișierul .env (dacă există în rădăcina proiectului)
    dotenv_path = os.path.join(director_proiect, ".env")
    if os.path.exists(dotenv_path):
        load_dotenv(dotenv_path)
        logging.info("Variabilele de mediu din .env au fost încărcate.")
    else:
        logging.info("Fișierul .env nu a fost găsit. Se vor folosi variabilele de mediu din sistem.")

    # 1. Determinare cale config.yaml și încărcare setări
    config_path = os.path.join(director_proiect, "config.yaml")
    
    if not os.path.exists(config_path):
        logging.error(f"Fișierul de configurare config.yaml nu a fost găsit la adresa: {config_path}")
        sys.exit(1)
        
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        logging.info("Configurarea a fost încărcată cu succes.")
    except Exception as e:
        logging.error(f"Eroare la citirea fișierului config.yaml: {e}")
        sys.exit(1)

    # 2. Colectare și deduplicare știri din feed-urile RSS
    logging.info("Pasul 1: Colectare și filtrare știri RSS...")
    stiri_colectate = descarca_si_filtreaza_stiri(config)
    
    # 3. Generare rezumate și traduceri (cu Caching, Batching și Fallbacks)
    stiri_rezumate = []
    docs_dir = os.path.join(director_proiect, "docs")
    
    if stiri_colectate:
        logging.info("Pasul 2: Generare rezumate (cu cache, batch și fallbacks)...")
        try:
            stiri_rezumate = proceseaza_si_rezuma_stiri(stiri_colectate, config, docs_dir)
        except Exception as e:
            logging.error(f"Eroare neașteptată în procesul de rezumare: {e}")
            # În caz de eroare critică, facem fallback manual pe tot setul
            stiri_rezumate = []
            for art in stiri_colectate:
                s_copy = art.copy()
                s_copy["translated_title"] = art["title"]
                s_copy["summary"] = None
                stiri_rezumate.append(s_copy)
    else:
        logging.info("Pasul 2: Nu s-au găsit știri noi în ultimele 24 de ore.")

    # 4. Trimitere mesaje pe Telegram
    # Trimitem pe Telegram doar dacă avem știri de trimis
    if stiri_rezumate:
        logging.info("Pasul 3: Trimitere digest pe Telegram...")
        try:
            trimite_digest_telegram(stiri_rezumate)
        except Exception as e:
            logging.error(f"Eroare neașteptată la trimiterea pe Telegram: {e}")
    else:
        logging.info("Pasul 3: Se sare peste trimiterea pe Telegram (lipsă știri).")

    # 5. Actualizare site web static în docs/
    logging.info("Pasul 4: Actualizare istoric JSON și site static (GitHub Pages)...")
    try:
        # Actualizăm fișierul de arhivă docs/data/archive.json
        arhiva = actualizeaza_arhiva(stiri_rezumate, docs_dir)
        # Regenerăm docs/index.html pe baza noii arhive
        construieste_site(arhiva, docs_dir)
    except Exception as e:
        logging.error(f"Eroare neașteptată la actualizarea site-ului web static: {e}")
        
    logging.info("=== Orchestratorul TechDigest și-a finalizat rularea cu succes ===")

if __name__ == "__main__":
    main()

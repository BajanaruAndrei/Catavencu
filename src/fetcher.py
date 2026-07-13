import feedparser
import time
import html
from datetime import datetime, timedelta, timezone
from bs4 import BeautifulSoup
import difflib
import logging

# Configurare logging cu UTF-8
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s", encoding="utf-8")

def curata_html(continut_html):
    """
    Elimină etichetele HTML dintr-un text folosind BeautifulSoup
    și normalizează spațiile goale.
    """
    if not continut_html:
        return ""
    try:
        soup = BeautifulSoup(continut_html, "html.parser")
        text = soup.get_text(separator=" ")
        return " ".join(text.split())
    except Exception as e:
        logging.warning(f"Eroare la curățarea HTML-ului: {e}")
        # Fallback simplu dacă bs4 eșuează
        import re
        text_curat = re.sub(r'<[^>]+>', ' ', continut_html)
        return " ".join(text_curat.split())

def obtine_data_utc(entry):
    """
    Extrage și convertește data publicării unei intrări RSS într-un obiect datetime UTC.
    """
    parsed_time = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed_time:
        try:
            # Struct_time returnat de feedparser este normalizat în UTC
            return datetime(*parsed_time[:6], tzinfo=timezone.utc)
        except Exception as e:
            logging.warning(f"Eroare la conversia datei parse-ate: {e}")
    
    # Fallback pe data curentă dacă nu poate fi determinată
    return datetime.now(timezone.utc)

def are_similaritate(titlu1, titlu2, prag=0.6):
    """
    Verifică dacă două titluri sunt similare peste un sau sub un prag folosind SequenceMatcher.
    """
    t1 = titlu1.lower().strip()
    t2 = titlu2.lower().strip()
    similitudine = difflib.SequenceMatcher(None, t1, t2).ratio()
    return similitudine >= prag

def descarca_si_filtreaza_stiri(config):
    """
    Descarcă feed-urile RSS configurate, filtrează articolele din ultimele 24 de ore,
    limitează articolele la maximum 4 per sursă, le deduplică și le returnează
    organizate în internaționale și românești.
    """
    max_stiri = config.get("settings", {}).get("max_news", 15)
    prag_similitudine = config.get("settings", {}).get("similarity_threshold", 0.6)
    max_per_sursa = config.get("settings", {}).get("max_news_per_source", 4)
    
    surse = config.get("sources", {})
    stiri_internationale = []
    stiri_romanesti = []
    
    acum = datetime.now(timezone.utc)
    limita_timp = acum - timedelta(hours=24)
    
    # 1. Descarcă feed-urile internaționale
    for sursa in surse.get("international", []):
        nume_sursa = sursa.get("name")
        url_sursa = sursa.get("url")
        logging.info(f"Se descarcă feed-ul internațional: {nume_sursa} ({url_sursa})")
        
        numar_articole_sursa = 0
        try:
            feed = feedparser.parse(url_sursa)
            for entry in feed.entries:
                if numar_articole_sursa >= max_per_sursa:
                    logging.info(f"S-a atins limita de {max_per_sursa} știri pentru sursa {nume_sursa}.")
                    break
                    
                data_pub = obtine_data_utc(entry)
                if data_pub >= limita_timp:
                    # Aplicăm html.unescape pe titlu și conținut pentru a rezolva entitățile precum &#8217;
                    titlu_raw = entry.get("title", "")
                    titlu_unescaped = html.unescape(titlu_raw)
                    
                    continut_raw = entry.get("summary") or entry.get("description") or ""
                    continut_unescaped = html.unescape(curata_html(continut_raw))
                    
                    stiri_internationale.append({
                        "title": titlu_unescaped,
                        "url": entry.get("link", ""),
                        "source": nume_sursa,
                        "published": data_pub,
                        "content": continut_unescaped,
                        "category": "international"
                    })
                    numar_articole_sursa += 1
        except Exception as e:
            logging.error(f"Eroare la descărcarea feed-ului {nume_sursa}: {e}")

    # 2. Descarcă feed-urile românești
    for sursa in surse.get("romanian", []):
        nume_sursa = sursa.get("name")
        url_sursa = sursa.get("url")
        logging.info(f"Se descarcă feed-ul românesc: {nume_sursa} ({url_sursa})")
        
        numar_articole_sursa = 0
        try:
            feed = feedparser.parse(url_sursa)
            for entry in feed.entries:
                if numar_articole_sursa >= max_per_sursa:
                    logging.info(f"S-a atins limita de {max_per_sursa} știri pentru sursa {nume_sursa}.")
                    break
                    
                data_pub = obtine_data_utc(entry)
                if data_pub >= limita_timp:
                    titlu_raw = entry.get("title", "")
                    titlu_unescaped = html.unescape(titlu_raw)
                    
                    continut_raw = entry.get("summary") or entry.get("description") or ""
                    continut_unescaped = html.unescape(curata_html(continut_raw))
                    
                    stiri_romanesti.append({
                        "title": titlu_unescaped,
                        "url": entry.get("link", ""),
                        "source": nume_sursa,
                        "published": data_pub,
                        "content": continut_unescaped,
                        "category": "romanian"
                    })
                    numar_articole_sursa += 1
        except Exception as e:
            logging.error(f"Eroare la descărcarea feed-ului {nume_sursa}: {e}")

    # 3. Deduplicare articole
    # Procesăm întâi cele internaționale (prioritate mare), apoi cele românești
    articole_acceptate = []
    
    def adauga_cu_deduplicare(articole):
        for art in articole:
            este_duplicat = False
            for acc in articole_acceptate:
                if are_similaritate(art["title"], acc["title"], prag_similitudine):
                    este_duplicat = True
                    logging.info(f"Articol ignorat ca duplicat: '{art['title']}' (similar cu '{acc['title']}')")
                    break
            if not este_duplicat:
                articole_acceptate.append(art)

    # Adăugăm întâi internaționale, apoi românești
    adauga_cu_deduplicare(stiri_internationale)
    
    # Reținem indexul unde se termină știrile internaționale acceptate
    index_int = len(articole_acceptate)
    
    # Adăugăm știrile românești
    adauga_cu_deduplicare(stiri_romanesti)
    
    # Separăm știrile finale acceptate
    # Limita totală este max_stiri (de exemplu 15)
    # Păstrăm ordinea: întâi internaționale, apoi românești, până la limita maximă
    stiri_int_finale = articole_acceptate[:index_int]
    stiri_ro_finale = articole_acceptate[index_int:]
    
    # Reasamblăm limitând la numărul maxim cerut
    stiri_finale = (stiri_int_finale + stiri_ro_finale)[:max_stiri]
    
    logging.info(f"Total știri colectate și filtrate după deduplicare și limitare pe sursă: {len(stiri_finale)}")
    return stiri_finale

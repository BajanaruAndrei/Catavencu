import feedparser
import time
import html
import requests
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
    Verifică dacă două titluri sunt similare peste un prag folosind SequenceMatcher.
    """
    t1 = titlu1.lower().strip()
    t2 = titlu2.lower().strip()
    similitudine = difflib.SequenceMatcher(None, t1, t2).ratio()
    return similitudine >= prag

def descarca_si_filtreaza_stiri(config):
    """
    Descarcă feed-urile RSS configurate și filtrează articolele din ultimele ore configurate.
    Deduplică titlurile foarte similare, dar nu limitează totalul sau per sursă în acest pas.
    """
    prag_similitudine = config.get("settings", {}).get("similarity_threshold", 0.6)
    ore_vechime = config.get("settings", {}).get("ore_vechime", 24)
    
    surse = config.get("sources", {})
    stiri_colectate = []
    
    acum = datetime.now(timezone.utc)
    limita_timp = acum - timedelta(hours=ore_vechime)
    
    # 1. Descarcă feed-urile internaționale
    for sursa in surse.get("international", []):
        nume_sursa = sursa.get("name")
        url_sursa = sursa.get("url")
        logging.info(f"Se descarcă feed-ul internațional: {nume_sursa} ({url_sursa})")
        
        numar_articole_sursa = 0
        try:
            r = requests.get(url_sursa, timeout=10, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) TechDigestAggregator'})
            if r.status_code != 200:
                logging.warning(f"Sursa '{nume_sursa}' a returnat codul HTTP {r.status_code}. Se trece mai departe.")
                continue
                
            feed = feedparser.parse(r.content)
            for entry in feed.entries:
                data_pub = obtine_data_utc(entry)
                if data_pub >= limita_timp:
                    titlu_unescaped = html.unescape(entry.get("title", ""))
                    continut_unescaped = html.unescape(curata_html(entry.get("summary") or entry.get("description") or ""))
                    
                    stiri_colectate.append({
                        "title": titlu_unescaped,
                        "url": entry.get("link", ""),
                        "source": nume_sursa,
                        "published": data_pub,
                        "content": continut_unescaped,
                        "category": "international"
                    })
                    numar_articole_sursa += 1
            logging.info(f"Sursa '{nume_sursa}' a returnat {numar_articole_sursa} articole valide în ultimele {ore_vechime} ore.")
        except Exception as e:
            logging.warning(f"Eroare sau timeout la descărcarea feed-ului '{nume_sursa}': {e}. Se continuă cu restul surselor.")

    # 2. Descarcă feed-urile românești
    for sursa in surse.get("romanian", []):
        nume_sursa = sursa.get("name")
        url_sursa = sursa.get("url")
        logging.info(f"Se descarcă feed-ul românesc: {nume_sursa} ({url_sursa})")
        
        numar_articole_sursa = 0
        try:
            r = requests.get(url_sursa, timeout=10, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) TechDigestAggregator'})
            if r.status_code != 200:
                logging.warning(f"Sursa '{nume_sursa}' a returnat codul HTTP {r.status_code}. Se trece mai departe.")
                continue
                
            feed = feedparser.parse(r.content)
            for entry in feed.entries:
                data_pub = obtine_data_utc(entry)
                if data_pub >= limita_timp:
                    titlu_unescaped = html.unescape(entry.get("title", ""))
                    continut_unescaped = html.unescape(curata_html(entry.get("summary") or entry.get("description") or ""))
                    
                    stiri_colectate.append({
                        "title": titlu_unescaped,
                        "url": entry.get("link", ""),
                        "source": nume_sursa,
                        "published": data_pub,
                        "content": continut_unescaped,
                        "category": "romanian"
                    })
                    numar_articole_sursa += 1
            logging.info(f"Sursa '{nume_sursa}' a returnat {numar_articole_sursa} articole valide în ultimele {ore_vechime} ore.")
        except Exception as e:
            logging.warning(f"Eroare sau timeout la descărcarea feed-ului '{nume_sursa}': {e}. Se continuă cu restul surselor.")

    # 3. Deduplicare titluri (comparând similaritatea titlurilor)
    # Procesăm în ordinea colectării (cronologic sau cum vin)
    articole_deduplicate = []
    for art in stiri_colectate:
        este_duplicat = False
        for acc in articole_deduplicate:
            if are_similaritate(art["title"], acc["title"], prag_similitudine):
                este_duplicat = True
                logging.info(f"Articol ignorat ca duplicat: '{art['title']}' (similar cu '{acc['title']}')")
                break
        if not este_duplicat:
            articole_deduplicate.append(art)
            
    logging.info(f"Total știri colectate și deduplicate în brut: {len(articole_deduplicate)}")
    return articole_deduplicate

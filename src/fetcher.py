import feedparser
import time
import html
import requests
import string
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

def normalizeaza_titlu(titlu):
    """
    Normalizează titlul: trece în lowercase, elimină punctuația
    și elimină cuvintele de umplutură uzuale (engleză și română).
    """
    t = titlu.lower()
    t = t.translate(str.maketrans('', '', string.punctuation))
    cuvinte_umplutura = {
        # Engleză
        "a", "an", "the", "and", "or", "but", "in", "on", "at", "for", "with", "to", "is", "are", 
        "was", "were", "of", "about", "by", "from", "that", "this", "these", "those", "it", "its", "new",
        "why", "how", "what", "where", "who", "when", "which", "out", "not", "dont", "best", "will", "more", "arent",
        # Română
        "o", "un", "unui", "unei", "si", "sau", "dar", "in", "pe", "la", "pentru", "cu", "de", "din", 
        "este", "sunt", "era", "erau", "ca", "sa", "acest", "aceasta", "acele", "aceste", "lui", "nou",
        "cel", "mai", "mare", "care", "cum", "ce", "cine", "cand", "unde", "fost", "prin", "daca", "fara", 
        "mult", "multi", "multe", "tot", "toti", "toate", "dupa", "cumpara", "pret", "lei", "euro"
    }
    cuvinte = t.split()
    return [w for w in cuvinte if w not in cuvinte_umplutura and len(w) > 2]

def verifica_duplicat(art1, art2, prag=0.6):
    """
    Verifică dacă două articole sunt duplicate din punct de vedere algoritmic.
    Întoarce (True, motiv) dacă sunt duplicate, altfel (False, "").
    """
    t1_norm = normalizeaza_titlu(art1["title"])
    t2_norm = normalizeaza_titlu(art2["title"])
    
    # 1. Comparare SequenceMatcher pe titlurile normalizate
    norm1 = " ".join(t1_norm)
    norm2 = " ".join(t2_norm)
    similitudine = difflib.SequenceMatcher(None, norm1, norm2).ratio()
    if similitudine >= prag:
        return True, f"similaritate fuzzy ({similitudine:.2f} >= {prag})"
        
    # 2. Verificare dacă au în comun 3 sau mai multe cuvinte-cheie semnificative
    set1 = set(t1_norm)
    set2 = set(t2_norm)
    cuvinte_comune = set1.intersection(set2)
    if len(cuvinte_comune) >= 3:
        return True, f"au în comun {len(cuvinte_comune)} cuvinte-cheie: {list(cuvinte_comune)}"
        
    return False, ""

def descarca_si_filtreaza_stiri(config):
    """
    Descarcă feed-urile RSS configurate și filtrează articolele din ultimele ore configurate.
    Deduplică titlurile foarte similare respectând prioritatea surselor.
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

    # 3. Deduplicare articole respectând prioritatea surselor din config.yaml
    prioritate_surse = {}
    idx = 0
    for grup in ["international", "romanian"]:
        for s in surse.get(grup, []):
            prioritate_surse[s.get("name")] = idx
            idx += 1
            
    # Sortăm articolele în funcție de ordinea sursei în config (index mai mic = prioritate mai mare)
    stiri_sortate = sorted(stiri_colectate, key=lambda x: prioritate_surse.get(x["source"], 999))
    
    articole_deduplicate = []
    for art in stiri_sortate:
        este_duplicat = False
        for acc in articole_deduplicate:
            dub, motiv = verifica_duplicat(art, acc, prag_similitudine)
            if dub:
                este_duplicat = True
                logging.info(
                    f"Articol eliminat ca duplicat: '{art['title']}' ({art['source']}) "
                    f"-> similar cu '{acc['title']}' ({acc['source']}) din cauza: {motiv}"
                )
                break
        if not este_duplicat:
            articole_deduplicate.append(art)
            
    logging.info(f"Total știri colectate și deduplicate: {len(articole_deduplicate)}")
    return articole_deduplicate

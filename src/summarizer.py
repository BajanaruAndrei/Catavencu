import os
import sys
import time
import json
import logging
import re
from pydantic import BaseModel
from typing import List

# Configurare logging cu UTF-8
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s", encoding="utf-8")

# Schema Pydantic pentru ieșirea structurată (Gemini)
class NewsSummaryItem(BaseModel):
    id: int
    titlu_ro: str
    rezumat_ro: str

class BatchNewsResponse(BaseModel):
    results: List[NewsSummaryItem]

def incarca_cache(docs_dir):
    """
    Încarcă cache-ul local de știri de pe disc.
    """
    cache_file = os.path.join(docs_dir, "data", "cache.json")
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Eroare la încărcarea cache-ului: {e}")
    return {}

def salveaza_cache(cache, docs_dir):
    """
    Salvează cache-ul de știri pe disc.
    """
    cache_dir = os.path.join(docs_dir, "data")
    os.makedirs(cache_dir, exist_ok=True)
    cache_file = os.path.join(cache_dir, "cache.json")
    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
        logging.info("Cache-ul de traduceri a fost salvat pe disc.")
    except Exception as e:
        logging.error(f"Eroare la salvarea cache-ului: {e}")

def curata_si_parseaza_json(text_raspuns):
    """
    Curăță eventualele blocuri de cod markdown (ex: ```json ... ```) și parsează JSON-ul.
    """
    cleaned = text_raspuns.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\n", "", cleaned)
        cleaned = re.sub(r"\n```$", "", cleaned)
    return json.loads(cleaned.strip())

def ruleaza_batch_gemini(articole, config):
    """
    Apelează Gemini API cu un prompt batch pentru a procesa toate știrile dintr-un singur call.
    """
    from google import genai
    from google.genai import types

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("Cheia GEMINI_API_KEY nu este setată.")

    model_name = config.get("gemini", {}).get("model", "gemini-3.5-flash")
    temperature = config.get("gemini", {}).get("temperature", 0.2)
    
    # Pregătim formatul compact de trimitere
    stiri_trimise = []
    for idx, art in enumerate(articole):
        stiri_trimise.append({
            "id": idx + 1,
            "titlu": art["title"],
            "continut": art["content"][:800]  # Limităm dimensiunea conținutului
        })
        
    prompt = f"""
Tradu titlurile următoarelor știri în limba română și generează un rezumat scurt în limba română pentru fiecare.

Știri de procesat (în format JSON):
{json.dumps(stiri_trimise, ensure_ascii=False, indent=2)}

Reguli de traducere și rezumat:
1. Scrie într-o română corectă gramatical, cu acord corect între substantiv, adjectiv și articol. Verifică cu atenție genul substantivelor (de exemplu: "această aplicație", nu "acest aplicație").
2. Dacă textul sursă al unei știri nu oferă informații sau detalii suplimentare utile dincolo de ceea ce este scris în titlu, returnează rezumat_ro = "" (string gol). Nu adăuga generalități, speculații sau tautologii de tipul "articolul discută despre...".

Reguli Anti-Halucinare stricte:
1. Rezumă DOAR informațiile din textul fiecărei știri. NU adăuga informații, cifre, nume sau date care nu apar în text. Dacă textul unei știri este prea scurt sau insuficient, scrie un rezumat extrem de scurt sau folosește doar informația disponibilă, fără a inventa nimic.
2. Fiecare rezumat trebuie să aibă maximum 2-3 propoziții clare și concise.
3. Răspunsul tău trebuie să fie STRICT un obiect sau o listă JSON în formatul specificat, fără text explicativ suplimentar în afara JSON-ului.
"""

    # Configurăm clientul cu timeout de 60 de secunde
    client = genai.Client(api_key=api_key, http_options={'timeout': 60.0})
    
    max_retries = 2
    for attempt in range(max_retries + 1):
        try:
            logging.info(f"Se trimite batch-ul de {len(articole)} știri către Gemini ({model_name})...")
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=temperature,
                    response_mime_type="application/json",
                    response_schema=BatchNewsResponse,
                )
            )
            
            # Parsare răspuns
            rezultat = curata_si_parseaza_json(response.text)
            return rezultat.get("results", [])
        except Exception as e:
            err_str = str(e).lower()
            if "429" in err_str or "rate limit" in err_str or "exhausted" in err_str:
                if attempt < max_retries:
                    logging.warning(f"Rate limit atins în Gemini (429). Reîncercare {attempt + 1}/{max_retries} în 5 secunde...")
                    time.sleep(5)
                    continue
            raise e
            
    raise Exception("Numărul maxim de reîncercări a fost epuizat în Gemini API din cauza rate-limiting-ului.")

def ruleaza_batch_groq(articole, config):
    """
    Apelează Groq API (cu Llama 3) ca fallback cu un prompt batch.
    """
    from groq import Groq

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError("Cheia GROQ_API_KEY nu este setată.")

    model_name = config.get("groq", {}).get("model", "llama-3.3-70b-versatile")
    temperature = config.get("groq", {}).get("temperature", 0.2)

    stiri_trimise = []
    for idx, art in enumerate(articole):
        stiri_trimise.append({
            "id": idx + 1,
            "titlu": art["title"],
            "continut": art["content"][:800]
        })

    prompt = f"""
Tradu titlurile următoarelor știri în limba română și generează un rezumat scurt în limba română pentru fiecare.

Știri de procesat (în format JSON):
{json.dumps(stiri_trimise, ensure_ascii=False, indent=2)}

Reguli de traducere și rezumat:
1. Scrie într-o română corectă gramatical, cu acord corect între substantiv, adjectiv și articol. Verifică cu atenție genul substantivelor (de exemplu: "această aplicație", nu "acest aplicație").
2. Dacă textul sursă al unei știri nu oferă informații sau detalii suplimentare utile dincolo de ceea ce este scris în titlu, returnează rezumat_ro = "" (string gol). Nu adăuga generalități, speculații sau tautologii de tipul "articolul discută despre...".

Reguli Anti-Halucinare stricte:
1. Rezumă DOAR informațiile din textul fiecărei știri. NU adăuga informații, cifre, nume sau date care nu apar în text. Dacă textul unei știri este prea scurt sau insuficient, scrie un rezumat extrem de scurt sau folosește doar informația disponibilă, fără a inventa nimic.
2. Fiecare rezumat trebuie să aibă maximum 2-3 propoziții clare și concise.
3. Răspunsul tău trebuie să fie STRICT un obiect sau o listă JSON în formatul specificat, fără text explicativ suplimentar în afara JSON-ului.
"""

    # Configurăm clientul cu timeout de 60 de secunde
    client = Groq(api_key=api_key, timeout=60.0)

    max_retries = 2
    for attempt in range(max_retries + 1):
        try:
            logging.info(f"Se trimite batch-ul de {len(articole)} știri către Groq ({model_name})...")
            
            chat_completion = client.chat.completions.create(
                model=model_name,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a helpful translation and summarization assistant. You must respond ONLY with a JSON object containing a 'results' array where each item has 'id', 'titlu_ro', and 'rezumat_ro'. Do not write explanations outside of JSON."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=temperature,
                response_format={"type": "json_object"}
            )
            
            response_text = chat_completion.choices[0].message.content
            rezultat = curata_si_parseaza_json(response_text)
            return rezultat.get("results", [])
        except Exception as e:
            err_str = str(e).lower()
            if "429" in err_str or "rate limit" in err_str or "exhausted" in err_str:
                if attempt < max_retries:
                    logging.warning(f"Rate limit atins în Groq (429). Reîncercare {attempt + 1}/{max_retries} în 5 secunde...")
                    time.sleep(5)
                    continue
            raise e

    raise Exception("Numărul maxim de reîncercări a fost epuizat în Groq API din cauza rate-limiting-ului.")

def proceseaza_si_rezuma_stiri(stiri_colectate, config, docs_dir):
    """
    Procesează lista completă de știri colectate:
    1. Verifică cache-ul local pentru a evita apelurile API repetate.
    2. Grupează știrile uncached și le trimite în batch către providerul primar (Gemini).
    3. Dacă eșuează, trece la providerul secundar (Groq).
    4. Dacă ambele eșuează, folosește fallback-ul pe titlu original + lipsă rezumat.
    5. Actualizează cache-ul pe disc.
    """
    cache = incarca_cache(docs_dir)
    stiri_procesate = []
    articole_de_apelat = []
    
    # Pas 1: Separare știri din cache vs știri de apelat
    for stire in stiri_colectate:
        url = stire["url"]
        if url in cache:
            logging.info(f"Știrea '{stire['title']}' a fost găsită în cache. Se reutilizează traducerea.")
            stire_copie = stire.copy()
            stire_copie["translated_title"] = cache[url]["translated_title"]
            stire_copie["summary"] = cache[url]["summary"]
            stiri_procesate.append(stire_copie)
        else:
            # Va fi procesat în batch
            articole_de_apelat.append(stire)
            
    # Dacă nu avem știri noi de procesat prin LLM, terminăm rapid
    if not articole_de_apelat:
        logging.info("Toate știrile au fost preluate direct din cache. Nu a fost necesar niciun apel LLM.")
        return stiri_procesate

    # Pas 2: Pregătirea rezultatelor fallback (în caz de erori API)
    rezultate_llm = None
    fallback_map = {}
    for idx, art in enumerate(articole_de_apelat):
        fallback_map[idx + 1] = {
            "translated_title": art["title"],
            "summary": None
        }

    # Pas 3: Lanțul de executare API (Gemini -> Groq -> Fallback)
    incercare_groq = False
    
    # 3.1 Apel Gemini
    try:
        results = ruleaza_batch_gemini(articole_de_apelat, config)
        # Convertim lista returnată într-un map pe baza id-ului
        rezultate_llm = {}
        for r in results:
            rezultate_llm[int(r.get("id"))] = {
                "translated_title": r.get("titlu_ro"),
                "summary": r.get("rezumat_ro")
            }
        logging.info("Batch-ul de știri a fost procesat cu succes prin Gemini.")
    except Exception as e:
        logging.error(f"Eroare completă la apelul batch Gemini: {e}. Se trece la Groq...")
        incercare_groq = True

    # 3.2 Apel Groq (dacă Gemini a eșuat)
    if incercare_groq:
        try:
            results = ruleaza_batch_groq(articole_de_apelat, config)
            rezultate_llm = {}
            for r in results:
                rezultate_llm[int(r.get("id"))] = {
                    "translated_title": r.get("titlu_ro"),
                    "summary": r.get("rezumat_ro")
                }
            logging.info("Batch-ul de știri a fost procesat cu succes prin Groq (Llama).")
        except Exception as e_groq:
            logging.error(f"Eroare completă la apelul batch Groq: {e_groq}. Se va folosi fallback-ul local.")
            # rezultate_llm rămâne None, se va aplica fallback_map

    # Pas 4: Combinare rezultate finalizate și actualizare cache
    harta_finala = rezultate_llm if rezultate_llm else fallback_map
    
    for idx, art in enumerate(articole_de_apelat):
        stire_noua = art.copy()
        date_traducere = harta_finala.get(idx + 1, fallback_map[idx + 1])
        
        stire_noua["translated_title"] = date_traducere["translated_title"]
        stire_noua["summary"] = date_traducere["summary"]
        
        # Salvăm în cache doar dacă traducerea a reușit (nu a intrat pe fallback-ul lipsă rezumat)
        if stire_noua["summary"] is not None:
            cache[stire_noua["url"]] = {
                "translated_title": stire_noua["translated_title"],
                "summary": stire_noua["summary"]
            }
            
        stiri_procesate.append(stire_noua)
        
    # Salvăm noul cache pe disc
    salveaza_cache(cache, docs_dir)
    
    return stiri_procesate

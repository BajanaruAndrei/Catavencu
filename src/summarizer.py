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

# Schema Pydantic pentru ieșirea structurată (Gemini) - Traducere & Rezumat
class NewsSummaryItem(BaseModel):
    id: int
    titlu_ro: str
    rezumat_ro: str

class BatchNewsResponse(BaseModel):
    results: List[NewsSummaryItem]

class DuplicateGroup(BaseModel):
    eveniment: str
    ids: List[int]
    id_pastrat: int

# Schema Pydantic pentru ordonare/relevanță (Gemini)
class RankedArticlesResponse(BaseModel):
    grupuri_duplicate: List[DuplicateGroup]
    ordine_finala: List[int]

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

# === ORDONARE ȘTIȚI DUPĂ RELEVANȚĂ / IMPORTANȚĂ ===

def ordoneaza_stiri_dupa_relevanta(stiri, config):
    """
    Ordonează o listă completă de articole folosind LLM (Gemini sau Groq ca fallback)
    pe baza importanței jurnalistice și grupează semantic duplicatele.
    """
    if not stiri:
        return []
        
    logging.info(f"Se începe ordonarea după relevanță pentru {len(stiri)} știri...")
    
    # 1. Pregătirea listei compacte pentru LLM
    stiri_compacte = []
    for idx, art in enumerate(stiri):
        stiri_compacte.append({
            "id": idx + 1,
            "titlu": art["title"],
            "sursa": art["source"],
            "regiune": "romaneasca" if art["category"] == "romanian" else "internationala",
            "descriere": art["content"][:250]  # Suficient pentru relevanță
        })
        
    prompt = f"""
Ești un expert jurnalist în tehnologie și redactor-șef. Sarcina ta este să ordonezi o listă de articole după importanța, impactul și relevanța lor pentru publicul pasionat de tehnologie, și să identifici duplicatele semantice.

Instrucțiuni de deduplicare semantică:
- Grupează articolele care relatează ACELAȘI EVENIMENT, indiferent de limbă, traducere sau de formularea titlului.
- De exemplu, un articol de pe o sursă românească și unul de pe o sursă internațională care vorbesc despre același anunț (cum ar fi Gemini integrat în Waze) sunt DUPLICATE și trebuie grupate împreună.
- Pentru fiecare grup de duplicate, specifică un nume scurt pentru "eveniment", lista completă de "ids" ale duplicatelor și alege un singur "id_pastrat" (cel mai complet, detaliat și informativ articol dintre ele).

Criterii de importanță (pentru restul articolelor):
- Prioritate MARE: Lansări majore de produse/tehnologii, anunțuri AI importante, decizii de reglementare cu impact larg (ex. decizii UE sau FTC), breșe de securitate sau scurgeri de date majore, achiziții sau mișcări importante ale marilor companii din industrie (Apple, Google, Microsoft, Meta, Nvidia, Tesla etc.).
- Prioritate MICĂ: Recenzii minore sau de accesorii, oferte comerciale/reduceri locale, clickbait, opinii personale ale autorilor, ghiduri practice sau liste de genul "cel mai bun X din 2026".

Articole de ordonat (în format JSON):
{json.dumps(stiri_compacte, ensure_ascii=False, indent=2)}

Regulă strictă anti-halucinare:
Răspunsul tău trebuie să fie STRICT un obiect JSON cu structura cerută.
1. "grupuri_duplicate": O listă de obiecte reprezentând grupurile de duplicate, fiecare cu "eveniment", "ids" și "id_pastrat".
2. "ordine_finala": O listă ordonată descrescător după importanță ce conține ID-urile articolelor.
3. Returnează EXCLUSIV ID-uri numerice din lista primită. NU inventa articole și nu returna ID-uri inexistente.
"""

    grupuri_duplicate = []
    ordine_finala = []
    erou_gemini = False
    
    # 1.1 Încercăm Gemini
    api_key_gemini = os.environ.get("GEMINI_API_KEY")
    if api_key_gemini:
        from google import genai
        from google.genai import types
        model_name = config.get("gemini", {}).get("model", "gemini-3.5-flash")
        temperature = config.get("gemini", {}).get("temperature", 0.2)
        
        client = genai.Client(api_key=api_key_gemini, http_options={'timeout': 60.0})
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                logging.info(f"Se trimite cererea de ordonare către Gemini ({model_name})...")
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=temperature,
                        response_mime_type="application/json",
                        response_schema=RankedArticlesResponse,
                    )
                )
                rezultat = curata_si_parseaza_json(response.text)
                grupuri_duplicate = rezultat.get("grupuri_duplicate", [])
                ordine_finala = rezultat.get("ordine_finala", [])
                logging.info("Ordonarea și deduplicarea semantică s-au efectuat prin Gemini.")
                break
            except Exception as e:
                err_str = str(e).lower()
                if "429" in err_str or "rate limit" in err_str or "exhausted" in err_str:
                    if attempt < max_retries:
                        logging.warning(f"Rate limit Gemini (429) la ordonare. Reîncercare {attempt + 1}/{max_retries} în 5 secunde...")
                        time.sleep(5)
                        continue
                logging.error(f"Apelul de ordonare Gemini a eșuat: {e}")
                erou_gemini = True
                break
    else:
        erou_gemini = True

    # 1.2 Încercăm Groq ca fallback
    if erou_gemini or (not ordine_finala and not grupuri_duplicate):
        api_key_groq = os.environ.get("GROQ_API_KEY")
        if api_key_groq:
            from groq import Groq
            model_name = config.get("groq", {}).get("model", "llama-3.3-70b-versatile")
            temperature = config.get("groq", {}).get("temperature", 0.2)
            
            client = Groq(api_key=api_key_groq, timeout=60.0)
            max_retries = 2
            for attempt in range(max_retries + 1):
                try:
                    logging.info(f"Se trimite cererea de ordonare către Groq ({model_name})...")
                    chat_completion = client.chat.completions.create(
                        model=model_name,
                        messages=[
                            {
                                "role": "system",
                                "content": "You are a redactor-in-chief assistant. You must respond ONLY with a JSON object matching the RankedArticlesResponse schema: {\"grupuri_duplicate\": [{\"eveniment\": \"...\", \"ids\": [...], \"id_pastrat\": ...}], \"ordine_finala\": [...]}. Do not write explanations outside of JSON."
                            },
                            {
                                "role": "user",
                                "content": prompt
                            }
                        ],
                        temperature=temperature,
                        response_format={"type": "json_object"}
                    )
                    rezultat = curata_si_parseaza_json(chat_completion.choices[0].message.content)
                    grupuri_duplicate = rezultat.get("grupuri_duplicate", [])
                    ordine_finala = rezultat.get("ordine_finala", [])
                    logging.info("Ordonarea și deduplicarea semantică s-au efectuat prin Groq.")
                    break
                except Exception as e:
                    err_str = str(e).lower()
                    if "429" in err_str or "rate limit" in err_str or "exhausted" in err_str:
                        if attempt < max_retries:
                            logging.warning(f"Rate limit Groq (429) la ordonare. Reîncercare {attempt + 1}/{max_retries} în 5 secunde...")
                            time.sleep(5)
                            continue
                    logging.error(f"Apelul de ordonare Groq a eșuat: {e}")
                    break

    id_to_art = {idx + 1: art for idx, art in enumerate(stiri)}

    # 2. PROCESARE ȘI VALIDARE DETECTARE DUPLICATE SEMANTICE
    articole_de_eliminat = set()
    
    if grupuri_duplicate:
        logging.info("=== GRUPURI DE DUPLICATE SEMANTICE DETECTATE ===")
        for grup in grupuri_duplicate:
            nume_eveniment = grup.get("eveniment", "Nespecificat")
            ids = grup.get("ids", [])
            id_pastrat = grup.get("id_pastrat")
            
            # Validări ID
            if not ids or id_pastrat is None:
                continue
                
            try:
                id_pastrat = int(id_pastrat)
                ids = [int(x) for x in ids]
            except (ValueError, TypeError):
                continue
                
            if id_pastrat not in id_to_art:
                logging.warning(f"  [AVERTISMENT] ID-ul păstrat {id_pastrat} pentru evenimentul '{nume_eveniment}' nu este valid.")
                continue
                
            art_pastrat = id_to_art[id_pastrat]
            detalii_eliminate = []
            
            for o_id in ids:
                if o_id in id_to_art and o_id != id_pastrat:
                    articole_de_eliminat.add(o_id)
                    detalii_eliminate.append(f"ID {o_id} '{id_to_art[o_id]['title']}' ({id_to_art[o_id]['source']})")
                    
            if detalii_eliminate:
                logging.info(f"📍 Eveniment: '{nume_eveniment}'")
                logging.info(f"   ✅ Păstrat: ID {id_pastrat} '{art_pastrat['title']}' ({art_pastrat['source']})")
                for det in detalii_eliminate:
                    logging.info(f"   ❌ Eliminat: {det}")
        logging.info("================================================")

    # 3. CONSTRUIRE ORDINE FINALĂ CU VALIDARE STRICTĂ
    reordered_stiri = []
    seen_ids = set()
    
    # 3.1 Preluăm în ordinea prioritizată de LLM, validând ID-urile și excluzând duplicatele
    if ordine_finala:
        for o_id in ordine_finala:
            try:
                val_id = int(o_id)
                if val_id not in id_to_art:
                    logging.warning(f"  [AVERTISMENT] LLM-ul a returnat un ID invalid în ordine_finala: {o_id}")
                    continue
                if val_id in articole_de_eliminat:
                    continue  # Excludem duplicatele marcate semantice
                if val_id not in seen_ids:
                    reordered_stiri.append(id_to_art[val_id])
                    seen_ids.add(val_id)
            except (ValueError, TypeError):
                continue
                
    # 3.2 Adăugăm restul articolelor care nu au fost selectate de LLM, nu sunt duplicate și nu au fost încă adăugate
    rest_stiri = []
    for idx in range(1, len(stiri) + 1):
        if idx not in seen_ids and idx not in articole_de_eliminat:
            rest_stiri.append(id_to_art[idx])
            
    if not reordered_stiri:
        # Fallback cronologic complet: cele mai noi primele
        logging.warning("S-a apelat fallback-ul cronologic pentru ordonare.")
        reordered_stiri = sorted(stiri, key=lambda x: x["published"], reverse=True)
    else:
        # Alipim restul articolelor la finalul listei ordonate
        reordered_stiri.extend(rest_stiri)

    # 4. Aplicarea cotelor de selecție finală (Quota check)
    max_per_sursa = config.get("settings", {}).get("max_per_sursa", 4)
    max_int = config.get("settings", {}).get("max_internationale", 11)
    max_ro = config.get("settings", {}).get("max_romanesti", 4)
    
    international_selected = []
    romanian_selected = []
    source_counts = {}
    
    for art in reordered_stiri:
        sursa = art["source"]
        category = art["category"]
        
        # Verificăm limita pe sursă
        if source_counts.get(sursa, 0) >= max_per_sursa:
            continue
            
        if category == "international":
            if len(international_selected) < max_int:
                international_selected.append(art)
                source_counts[sursa] = source_counts.get(sursa, 0) + 1
        elif category == "romanian":
            if len(romanian_selected) < max_ro:
                romanian_selected.append(art)
                source_counts[sursa] = source_counts.get(sursa, 0) + 1
                
        # Oprim loop-ul devreme dacă cotele sunt pline
        if len(international_selected) >= max_int and len(romanian_selected) >= max_ro:
            break
            
    # Afișăm distribuția pe surse
    selected_stiri = international_selected + romanian_selected
    logging.info("--- Distribuție surse selectate ---")
    for src, count in source_counts.items():
        logging.info(f"- {src}: {count} articole")
        
    logging.info(f"Selecție finalizată: {len(international_selected)} internaționale, {len(romanian_selected)} românești. Total: {len(selected_stiri)}")
    return selected_stiri


# === REZUMATE ȘI TRADUCERE ===

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
            
    raise Exception("Numărul maxim de reîncercări a fost epuizat în Gemini API.")

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

    raise Exception("Numărul maxim de reîncercări a fost epuizat în Groq API.")

def proceseaza_si_rezuma_stiri(stiri_colectate, config, docs_dir):
    """
    Procesează lista selectată de știri:
    1. Verifică cache-ul local pentru a evita apelurile API repetate.
    2. Grupează știrile uncached și le trimite în batch către providerul primar (Gemini).
    3. Dacă eșuează, trece la providerul secundar (Groq).
    4. Actualizează cache-ul pe disc.
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
            articole_de_apelat.append(stire)
            
    if not articole_de_apelat:
        logging.info("Toate știrile au fost preluate direct din cache. Nu a fost necesar niciun apel LLM de traducere.")
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

    # 3.2 Apel Groq
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

    # Pas 4: Combinare rezultate finalizate și actualizare cache
    harta_finala = rezultate_llm if rezultate_llm else fallback_map
    
    for idx, art in enumerate(articole_de_apelat):
        stire_noua = art.copy()
        date_traducere = harta_finala.get(idx + 1, fallback_map[idx + 1])
        
        stire_noua["translated_title"] = date_traducere["translated_title"]
        stire_noua["summary"] = date_traducere["summary"]
        
        if stire_noua["summary"] is not None:
            cache[stire_noua["url"]] = {
                "translated_title": stire_noua["translated_title"],
                "summary": stire_noua["summary"]
            }
            
        stiri_procesate.append(stire_noua)
        
    salveaza_cache(cache, docs_dir)
    return stiri_procesate

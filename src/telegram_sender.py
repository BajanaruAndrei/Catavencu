import os
import requests
import logging
import html
from datetime import datetime

# Configurare logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def trimite_digest_telegram(stiri_rezumate):
    """
    Trimite digestul de știri pe canalul/chat-ul de Telegram configurat.
    Se folosește modul HTML, iar textul este curățat pentru a preveni erori de parsare.
    Dacă mesajul este prea mare (peste 4096 caractere), este împărțit în mai multe părți.
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    
    if not token or not chat_id:
        logging.warning("TELEGRAM_BOT_TOKEN sau TELEGRAM_CHAT_ID nu sunt setate. Se va sări peste trimiterea pe Telegram.")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    
    # Obținem data curentă în format românesc
    data_curenta = datetime.now().strftime("%d.%m.%Y")
    header = f"📰 <b>TechDigest — {data_curenta}</b>\n\n"
    
    mesaje_de_trimis = []
    mesaj_curent = header
    
    for idx, stire in enumerate(stiri_rezumate):
        emoji = "🌐" if stire.get("category") == "international" else "🇷🇴"
        
        # Escapăm titlul, rezumatul și sursa pentru a evita caractere HTML invalide (&, <, >)
        titlu = html.escape(stire.get("translated_title") or stire.get("title") or "")
        rezumat = stire.get("summary")
        if rezumat and rezumat.strip():
            rezumat = html.escape(rezumat.strip())
        else:
            rezumat = None
        sursa = html.escape(stire.get("source") or "")
        link = html.escape(stire.get("url") or "")
        
        # Construim blocul pentru știrea curentă
        text_stire = f"{emoji} <b>{titlu}</b>\n"
        if rezumat:
            text_stire += f"{rezumat}\n"
        text_stire += f"🔗 <a href=\"{link}\">Sursa: {sursa}</a>\n\n"
        
        # Verificăm limita Telegram (4096 caractere). Lăsăm o marjă de siguranță la 4000.
        if len(mesaj_curent) + len(text_stire) > 4000:
            mesaje_de_trimis.append(mesaj_curent)
            # Inițiem următorul segment cu antet simplificat de continuare
            mesaj_curent = f"📰 <b>TechDigest — {data_curenta} (Continuare)</b>\n\n" + text_stire
        else:
            mesaj_curent += text_stire

    # Adăugăm ultimul segment nefinalizat, dacă conține altceva decât antetul
    if mesaj_curent != header and not mesaj_curent.endswith("(Continuare)</b>\n\n"):
        mesaje_de_trimis.append(mesaj_curent)

    # Trimiterea efectivă a bucăților
    for i, msg in enumerate(mesaje_de_trimis):
        payload = {
            "chat_id": chat_id,
            "text": msg,
            "parse_mode": "HTML",
            "disable_web_page_preview": True  # Fără previzualizări mari pentru un aspect curat
        }
        
        logging.info(f"Se trimite segmentul {i+1}/{len(mesaje_de_trimis)} pe Telegram...")
        try:
            r = requests.post(url, json=payload, timeout=15)
            if r.status_code != 200:
                logging.error(f"Eroare Telegram API (HTTP {r.status_code}): {r.text}")
            else:
                logging.info(f"Segmentul {i+1} trimis cu succes.")
        except Exception as e:
            logging.error(f"Eroare la conexiunea cu Telegram API: {e}")

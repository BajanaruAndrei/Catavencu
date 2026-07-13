# TechDigest — Agregator Zilnic de Știri Tech (AI Powered)

**TechDigest** este un agregator de știri tech complet gratuit, care rulează o dată pe zi prin GitHub Actions. 
Proiectul colectează articole din surse internaționale și românești, le traduce și le rezumă în limba română folosind **Gemini API (gemini-2.5-flash)**, le trimite pe un canal/grup de Telegram printr-un Bot și le publică pe un site static modern, găzduit pe **GitHub Pages**.

---

## 🚀 Ghid de Configurare Pas cu Pas (100% GRATUIT)

Urmează pașii de mai jos pentru a pune în funcțiune propriul tău agregator TechDigest. Nu ai nevoie de un card bancar sau de servicii plătite.

### 1. Obținerea cheii Gemini API (Gratuit)
Gemini API oferă o limită generoasă în Free Tier (suficientă pentru rularea zilnică a acestui proiect).
1. Accesează [Google AI Studio](https://aistudio.google.com/).
2. Autentifică-te cu contul tău de Google.
3. Apasă pe butonul **Get API Key** (sau **Create API Key**).
4. Selectează **Create API Key in new project** sau alege un proiect existent.
5. Copiază cheia generată (va fi de forma `AIzaSy...`). Această cheie va fi secretul `GEMINI_API_KEY`.
> [!NOTE]
> În Free Tier, nu este necesar să introduci date de card bancar.

---

### 2. Crearea Botului de Telegram și Aflarea Chat ID-ului
Mesajele vor fi trimise automat de un bot de Telegram creat de tine.
1. Deschide aplicația Telegram și caută-l pe **@BotFather** (utilizatorul oficial cu bifă albastră).
2. Trimite comanda `/newbot` și urmează instrucțiunile:
   - Introdu un nume pentru bot (de exemplu: `TechDigest Daily`).
   - Introdu un username unic care trebuie să se termine în `bot` (de exemplu: `techdigest_my_personal_bot`).
3. BotFather îți va trimite un mesaj de confirmare care conține un **token API** (de forma `123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ`). Acesta este secretul `TELEGRAM_BOT_TOKEN`.
4. **Obținerea Chat ID-ului (unde vrei să primești mesajele):**
   - Poți trimite mesajele într-un chat privat cu botul, într-un grup sau pe un canal public.
   - **Pentru chat privat**: Caută botul tău pe Telegram, apasă pe **Start**. Apoi deschide în browser URL-ul: `https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/getUpdates` (înlocuiește `<TELEGRAM_BOT_TOKEN>` cu tokenul primit). Caută în textul JSON câmpul `"id"` din interiorul obiectului `"chat"`. Acela este `TELEGRAM_CHAT_ID` (un număr întreg pozitiv).
   - Alternativ, poți folosi un bot precum **@userinfobot** sau **@ShowJsonBot** pe Telegram. Dă-i start sau redirecționează un mesaj către el, și îți va spune instant ID-ul tău de utilizator.
   - **Pentru grup/canal**: Adaugă botul ca administrator în grupul/canalul respectiv. ID-ul canalelor începe de obicei cu `-100` (de exemplu: `-100123456789`). Poți afla ID-ul trimițând un mesaj pe canal, apoi accesând link-ul de `/getUpdates` de mai sus sau folosind boți auxiliari de Telegram adăugați temporar în grup.

---

### 3. Configurarea Secretelor în Repository-ul GitHub
Pentru ca GitHub Actions să ruleze scriptul în siguranță fără a expune cheile în cod:
1. Creează un nou repository pe GitHub și încarcă codul acestui proiect.
2. În pagina repository-ului tău, mergi la **Settings** (bara de sus a paginii).
3. În meniul din stânga, navighează la **Secrets and variables** -> **Actions**.
4. Apasă pe butonul verde **New repository secret**.
5. Adaugă pe rând următoarele trei secrete:
   - Nume: `GEMINI_API_KEY` | Valoare: Cheia API de la Google AI Studio
   - Nume: `TELEGRAM_BOT_TOKEN` | Valoare: Tokenul botului de la BotFather
   - Nume: `TELEGRAM_CHAT_ID` | Valoare: ID-ul chat-ului unde vrei să fie trimise știrile
6. Salvează fiecare secret.

---

### 4. Activarea GitHub Pages
Aceasta va publica site-ul tău static în mod public și gratuit pe internet.
1. În pagina repository-ului tău, accesează **Settings**.
2. Din meniul din stânga, selectează secțiunea **Pages**.
3. La secțiunea **Build and deployment**:
   - **Source**: Selectează **Deploy from a branch**.
   - **Branch**: Selectează branch-ul tău principal (de regulă `main` sau `master`).
   - În al doilea dropdown (care implicit este `/ (root)`), selectează folderul **`/docs`**.
4. Apasă pe **Save**.
5. În câteva minute, GitHub va genera site-ul. Link-ul tău va fi de forma `https://<username>.github.io/<repository-name>/`.
> [!IMPORTANT]
> GitHub Pages va funcționa doar după ce folderul `docs/` este creat și trimis în repository (deja inclus în structură). Rularea cu succes a workflow-ului va genera automat fișierele necesare în `docs/`.

---

### 5. Testarea Manuală a Workflow-ului (Înainte de Rularea Automată)
Nu este nevoie să aștepți ora 07:00 pentru a vedea dacă totul funcționează corect. Poți declanșa manual procesul:
1. Accesează tab-ul **Actions** în pagina repository-ului tău GitHub.
2. În lista din stânga, selectează workflow-ul **TechDigest Daily Aggregator**.
3. Vei vedea o bară deschisă la culoare cu un mesaj de notificare și un buton în dreapta numit **Run workflow**.
4. Apasă pe **Run workflow**, selectează branch-ul dorit și apasă pe butonul verde **Run workflow**.
5. Așteaptă 1-2 minute ca procesul să treacă prin toți pașii (Checkout, Setup Python, Rularea scriptului și Commit/Push).
6. Verifică-ți telefonul (Telegram) pentru a vedea digestul și accesează adresa GitHub Pages pentru a vedea site-ul actualizat.

---

## 🛠️ Structura Proiectului

- `.github/workflows/daily.yml` — Configurația GitHub Actions pentru rularea zilnică programată (07:00 ora României) și manuală.
- `src/main.py` — Orchestratorul principal care coordonează fetcherul, sumarizatorul, telegram_senderul și site_builderul.
- `src/fetcher.py` — Descarcă feed-urile RSS din `config.yaml`, filtrează știrile din ultimele 24 de ore și elimină duplicatele prin similitudinea titlurilor.
- `src/summarizer.py` — Se conectează la Gemini API, traduce titlurile și generează rezumate în română, aplicând reguli stricte anti-halucinare și backoff la erori de rată (429).
- `src/telegram_sender.py` — Formatează și trimite știrile pe Telegram, segmentând automat mesajele care depășesc limita de 4096 de caractere.
- `src/site_builder.py` — Salvează istoricul ultimelor 7 zile în `docs/data/archive.json` și generează site-ul static responsiv `docs/index.html`.
- `docs/` — Folderul care conține codul site-ului static găzduit pe GitHub Pages.
- `config.yaml` — Fișierul de configurare pentru sursele RSS și modelul AI.
- `requirements.txt` — Dependențele Python ale proiectului.

---

## 💻 Dezvoltare Locală și Testare

Dacă dorești să rulezi proiectul local pe calculatorul tău:

1. Clonează repository-ul local.
2. Instalează dependențele:
   ```bash
   pip install -r requirements.txt
   ```
3. Configurează variabilele de mediu în terminalul tău (PowerShell sau Command Prompt / Bash):
   - **PowerShell (Windows)**:
     ```powershell
     $env:GEMINI_API_KEY="cheia_ta"
     $env:TELEGRAM_BOT_TOKEN="tokenul_tau"
     $env:TELEGRAM_CHAT_ID="id_chat"
     ```
   - **CMD (Windows)**:
     ```cmd
     set GEMINI_API_KEY=cheia_ta
     set TELEGRAM_BOT_TOKEN=tokenul_tau
     set TELEGRAM_CHAT_ID=id_chat
     ```
   - **Bash (Linux/macOS)**:
     ```bash
     export GEMINI_API_KEY="cheia_ta"
     export TELEGRAM_BOT_TOKEN="tokenul_tau"
     export TELEGRAM_CHAT_ID="id_chat"
     ```
4. Rulează scriptul principal:
   ```bash
   python src/main.py
   ```
5. Verifică fișierele nou create sau actualizate în folderul `docs/`.

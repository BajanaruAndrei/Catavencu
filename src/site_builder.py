import os
import json
import logging
import calendar
from datetime import datetime, timezone, timedelta

# Configurare logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def obtine_ora_romaniei():
    """
    Calculează timpul curent în fusul orar al României (Europe/Bucharest).
    Include trecerea la ora de vară (EEST = UTC+3) și de iarnă (EET = UTC+2) 
    fără a depinde de biblioteci externe precum pytz sau tzdata.
    """
    now_utc = datetime.now(timezone.utc)
    year = now_utc.year
    
    # Regula pentru ora de vară în România:
    # Începe în ultima duminică din martie (ora 01:00 UTC) și se termină în ultima duminică din octombrie (ora 01:00 UTC)
    
    # Determinăm ultima duminică din martie
    c = calendar.Calendar(firstweekday=calendar.MONDAY)
    month_march = c.monthdays2calendar(year, 3)
    last_sunday_march = [day for week in month_march for day, d_week in week if d_week == 6 and day > 0][-1]
    
    # Determinăm ultima duminică din octombrie
    month_october = c.monthdays2calendar(year, 10)
    last_sunday_oct = [day for week in month_october for day, d_week in week if d_week == 6 and day > 0][-1]
    
    dst_start = datetime(year, 3, last_sunday_march, 1, 0, 0, tzinfo=timezone.utc)
    dst_end = datetime(year, 10, last_sunday_oct, 1, 0, 0, tzinfo=timezone.utc)
    
    if dst_start <= now_utc < dst_end:
        offset = 3  # Ora de vară (EEST)
    else:
        offset = 2  # Ora de iarnă (EET)
        
    return now_utc + timedelta(hours=offset)

def actualizeaza_arhiva(stiri, docs_dir):
    """
    Actualizează fișierul `docs/data/archive.json` cu noile știri.
    Păstrează doar istoricul pentru ultimele 7 zile.
    """
    archive_dir = os.path.join(docs_dir, "data")
    os.makedirs(archive_dir, exist_ok=True)
    archive_file = os.path.join(archive_dir, "archive.json")
    
    archive = []
    if os.path.exists(archive_file):
        try:
            with open(archive_file, "r", encoding="utf-8") as f:
                archive = json.load(f)
        except Exception as e:
            logging.error(f"Eroare la încărcarea arhivei existente: {e}")
            archive = []

    acum_ro = obtine_ora_romaniei()
    data_cheie = acum_ro.strftime("%Y-%m-%d")
    
    luni_ro = {
        1: "Ianuarie", 2: "Februarie", 3: "Martie", 4: "Aprilie", 5: "Mai", 6: "Iunie",
        7: "Iulie", 8: "August", 9: "Septembrie", 10: "Octombrie", 11: "Noiembrie", 12: "Decembrie"
    }
    data_formatata = f"{acum_ro.day} {luni_ro[acum_ro.month]} {acum_ro.year}"
    
    # Serializăm știrile pentru JSON
    stiri_serializate = []
    for s in stiri:
        stiri_serializate.append({
            "title": s.get("title"),
            "translated_title": s.get("translated_title"),
            "url": s.get("url"),
            "source": s.get("source"),
            "published": s.get("published").isoformat() if isinstance(s.get("published"), datetime) else s.get("published"),
            "summary": s.get("summary"),
            "category": s.get("category")
        })
        
    # Verificăm dacă există deja ziua curentă în arhivă pentru a o actualiza
    gasit = False
    for i, entry in enumerate(archive):
        if entry.get("date") == data_cheie:
            archive[i] = {
                "date": data_cheie,
                "date_formatted": data_formatata,
                "news": stiri_serializate
            }
            gasit = True
            break
            
    if not gasit:
        # Adăugăm la începutul listei pentru ca cele mai noi zile să fie primele
        archive.insert(0, {
            "date": data_cheie,
            "date_formatted": data_formatata,
            "news": stiri_serializate
        })
        
    # Păstrăm maximum 7 zile
    archive = archive[:7]
    
    try:
        with open(archive_file, "w", encoding="utf-8") as f:
            json.dump(archive, f, ensure_ascii=False, indent=2)
        logging.info("Arhiva JSON actualizată cu succes.")
    except Exception as e:
        logging.error(f"Eroare la salvarea arhivei JSON: {e}")
        
    return archive

def construieste_site(archive, docs_dir):
    """
    Generează fișierul `docs/index.html` static pe baza arhivei de 7 zile.
    Creează un design responsive premium cu dark mode și tab-uri interactive.
    """
    os.makedirs(docs_dir, exist_ok=True)
    html_file = os.path.join(docs_dir, "index.html")
    
    # Construire butoane tab-uri și secțiuni de știri
    tabs_html = []
    days_sections_html = []
    
    for idx, zi in enumerate(archive):
        date_id = zi["date"]
        date_formatted = zi["date_formatted"]
        
        # Etichete prietenoase pentru primele 2 zile
        if idx == 0:
            label = "Azi"
        elif idx == 1:
            label = "Ieri"
        else:
            # Formatăm data scurt: de ex. "13 Iul"
            parti = date_formatted.split()
            label = f"{parti[0]} {parti[1][:3]}"
            
        active_class = "active" if idx == 0 else ""
        
        # Buton Tab
        tabs_html.append(f"""
        <button id="tab-{date_id}" class="tab-btn {active_class}" onclick="showDay('{date_id}')">
            <span class="tab-label">{label}</span>
            <span class="tab-date">{date_formatted}</span>
        </button>
        """)
        
        # Secțiune Știri pentru această zi
        news_cards = []
        for stire in zi["news"]:
            is_ro = stire.get("category") == "romanian"
            badge_class = "badge-ro" if is_ro else "badge-int"
            badge_text = "România" if is_ro else "Internațional"
            
            titlu = stire.get("translated_title") or stire.get("title") or "Fără titlu"
            titlu_original = stire.get("title")
            rezumat = stire.get("summary")
            sursa = stire.get("source") or "Sursă necunoscută"
            url = stire.get("url") or "#"
            
            # Formatare dată publicare (doar ora dacă e posibil)
            timp_afisat = ""
            try:
                dt = datetime.fromisoformat(stire.get("published"))
                timp_afisat = dt.strftime("%H:%M")
            except Exception:
                timp_afisat = ""
                
            detalii_timp = f'<span class="news-time">{timp_afisat}</span>' if timp_afisat else ""
            
            # Text rezumat
            rezumat_html = f'<p class="news-summary">{rezumat}</p>' if (rezumat and rezumat.strip()) else ''
            
            # Tooltip sau subtitlu cu titlul original dacă a fost tradus
            original_title_html = ""
            if titlu_original and titlu_original != titlu:
                original_title_html = f'<span class="original-title" title="Titlu Original">{titlu_original}</span>'
                
            news_cards.append(f"""
            <article class="news-card">
                <header class="news-card-header">
                    <span class="news-badge {badge_class}">{badge_text}</span>
                    <div class="news-meta">
                        <span class="news-source">{sursa}</span>
                        {detalii_timp}
                    </div>
                </header>
                <h3 class="news-title">
                    <a href="{url}" target="_blank" rel="noopener noreferrer">{titlu}</a>
                </h3>
                {original_title_html}
                {rezumat_html}
                <footer class="news-card-footer">
                    <a href="{url}" target="_blank" rel="noopener noreferrer" class="read-more-link">
                        Citește articolul original
                        <svg class="link-arrow" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <line x1="7" y1="17" x2="17" y2="7"></line>
                            <polyline points="7 7 17 7 17 17"></polyline>
                        </svg>
                    </a>
                </footer>
            </article>
            """)
            
        if not news_cards:
            news_cards.append("""
            <div class="no-news-placeholder">
                <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="opacity: 0.4; margin-bottom: 1rem;">
                    <rect x="2" y="3" width="20" height="18" rx="2" ry="2"></rect>
                    <line x1="16" y1="8" x2="16" y2="8"></line>
                    <line x1="8" y1="8" x2="12" y2="8"></line>
                    <line x1="8" y1="12" x2="16" y2="12"></line>
                    <line x1="8" y1="16" x2="14" y2="16"></line>
                </svg>
                <p>Nu s-au colectat știri în această zi.</p>
            </div>
            """)
            
        grid_layout = "no-grid" if not zi["news"] else ""
        days_sections_html.append(f"""
        <div id="day-{date_id}" class="day-section {active_class} {grid_layout}">
            {"".join(news_cards)}
        </div>
        """)

    tabs_str = "\n".join(tabs_html)
    sections_str = "\n".join(days_sections_html)
    
    an_curent = datetime.now().year
    
    html_content = f"""<!DOCTYPE html>
<html lang="ro">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TechDigest — Agregator de Știri Tech</title>
    <meta name="description" content="Rezumatul zilnic al celor mai importante știri din tehnologie, traduse și condensate automat în limba română cu inteligență artificială.">
    <!-- Google Fonts: Plus Jakarta Sans -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    
    <style>
        :root {{
            --bg-dark: #0b0f19;
            --bg-card: rgba(22, 28, 45, 0.7);
            --bg-nav: rgba(17, 24, 39, 0.85);
            --border-color: rgba(255, 255, 255, 0.08);
            --text-main: #f3f4f6;
            --text-muted: #9ca3af;
            --accent-gradient: linear-gradient(135deg, #a78bfa 0%, #6366f1 100%);
            --accent-indigo: #6366f1;
            --accent-purple: #a78bfa;
            
            --badge-int-bg: linear-gradient(135deg, rgba(99, 102, 241, 0.15), rgba(168, 85, 247, 0.15));
            --badge-int-border: rgba(99, 102, 241, 0.35);
            --badge-int-text: #c084fc;
            
            --badge-ro-bg: linear-gradient(135deg, rgba(239, 68, 68, 0.15), rgba(245, 158, 11, 0.15));
            --badge-ro-border: rgba(239, 68, 68, 0.35);
            --badge-ro-text: #f87171;
            
            --shadow-card: 0 4px 30px rgba(0, 0, 0, 0.25);
            --shadow-hover: 0 12px 30px rgba(99, 102, 241, 0.15);
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}

        body {{
            background-color: var(--bg-dark);
            color: var(--text-main);
            font-family: 'Plus Jakarta Sans', sans-serif;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            overflow-x: hidden;
            background-image: 
                radial-gradient(circle at 10% 20%, rgba(99, 102, 241, 0.05) 0%, transparent 40%),
                radial-gradient(circle at 90% 80%, rgba(167, 139, 250, 0.05) 0%, transparent 40%);
        }}

        header.main-header {{
            max-width: 1200px;
            width: 100%;
            margin: 0 auto;
            padding: 2.5rem 1.5rem 1.5rem 1.5rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 1.5rem;
        }}

        .brand-section {{
            display: flex;
            flex-direction: column;
            gap: 0.5rem;
        }}

        .brand-logo-title {{
            display: flex;
            align-items: center;
            gap: 0.75rem;
        }}

        .brand-logo {{
            background: var(--accent-gradient);
            padding: 0.5rem;
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 0 20px rgba(99, 102, 241, 0.4);
        }}

        .brand-title {{
            font-size: 2rem;
            font-weight: 800;
            letter-spacing: -0.025em;
            background: var(--accent-gradient);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}

        .brand-subtitle {{
            font-size: 0.95rem;
            color: var(--text-muted);
            max-width: 500px;
            line-height: 1.5;
        }}

        .header-actions {{
            display: flex;
            align-items: center;
            gap: 1rem;
        }}

        .telegram-btn {{
            background: #24A1DE;
            color: white;
            text-decoration: none;
            padding: 0.75rem 1.25rem;
            border-radius: 12px;
            font-size: 0.9rem;
            font-weight: 600;
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            box-shadow: 0 4px 15px rgba(36, 161, 222, 0.3);
            transition: transform 0.2s, box-shadow 0.2s;
        }}

        .telegram-btn:hover {{
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(36, 161, 222, 0.45);
        }}

        main.main-content {{
            flex: 1;
            max-width: 1200px;
            width: 100%;
            margin: 0 auto;
            padding: 1.5rem;
            display: flex;
            flex-direction: column;
            gap: 2rem;
        }}

        /* Zona de Navigare / Tab-uri */
        .archive-nav-wrapper {{
            overflow-x: auto;
            scrollbar-width: none; /* Firefox */
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 0.5rem;
        }}
        
        .archive-nav-wrapper::-webkit-scrollbar {{
            display: none; /* Safari / Chrome */
        }}

        .archive-nav {{
            display: flex;
            gap: 1rem;
            min-width: max-content;
            padding: 0.25rem 0;
        }}

        .tab-btn {{
            background: transparent;
            border: 1px solid var(--border-color);
            color: var(--text-muted);
            padding: 0.75rem 1.5rem;
            border-radius: 12px;
            cursor: pointer;
            display: flex;
            flex-direction: column;
            align-items: flex-start;
            gap: 0.25rem;
            transition: all 0.3s ease;
            backdrop-filter: blur(10px);
        }}

        .tab-btn:hover {{
            border-color: rgba(99, 102, 241, 0.4);
            color: var(--text-main);
            background: rgba(255, 255, 255, 0.02);
        }}

        .tab-btn.active {{
            background: var(--bg-card);
            border-color: var(--accent-indigo);
            color: var(--text-main);
            box-shadow: var(--shadow-card), 0 0 15px rgba(99, 102, 241, 0.1);
        }}

        .tab-label {{
            font-size: 1rem;
            font-weight: 700;
        }}

        .tab-date {{
            font-size: 0.75rem;
            opacity: 0.7;
        }}

        /* Sectiunea de zi */
        .day-section {{
            display: none;
            grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
            gap: 1.5rem;
            opacity: 0;
            transform: translateY(15px);
            transition: opacity 0.4s cubic-bezier(0.16, 1, 0.3, 1), transform 0.4s cubic-bezier(0.16, 1, 0.3, 1);
        }}

        .day-section.active {{
            display: grid;
            opacity: 1;
            transform: translateY(0);
        }}
        
        .day-section.no-grid {{
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 300px;
        }}

        /* Card-uri Stiri */
        .news-card {{
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 1.75rem;
            display: flex;
            flex-direction: column;
            gap: 1.25rem;
            box-shadow: var(--shadow-card);
            backdrop-filter: blur(12px);
            transition: transform 0.3s cubic-bezier(0.34, 1.56, 0.64, 1), box-shadow 0.3s, border-color 0.3s;
        }}

        .news-card:hover {{
            transform: translateY(-6px);
            box-shadow: var(--shadow-hover);
            border-color: rgba(99, 102, 241, 0.35);
        }}

        .news-card-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 0.75rem;
        }}

        .news-badge {{
            font-size: 0.75rem;
            font-weight: 700;
            padding: 0.35rem 0.75rem;
            border-radius: 20px;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}

        .badge-int {{
            background: var(--badge-int-bg);
            border: 1px solid var(--badge-int-border);
            color: var(--badge-int-text);
        }}

        .badge-ro {{
            background: var(--badge-ro-bg);
            border: 1px solid var(--badge-ro-border);
            color: var(--badge-ro-text);
        }}

        .news-meta {{
            display: flex;
            align-items: center;
            gap: 0.75rem;
            font-size: 0.8rem;
            color: var(--text-muted);
        }}

        .news-source {{
            font-weight: 600;
        }}

        .news-time {{
            opacity: 0.8;
            position: relative;
        }}
        
        .news-time::before {{
            content: "•";
            margin-right: 0.5rem;
            opacity: 0.5;
        }}

        .news-title {{
            font-size: 1.25rem;
            font-weight: 700;
            line-height: 1.4;
        }}

        .news-title a {{
            color: var(--text-main);
            text-decoration: none;
            transition: color 0.2s;
        }}

        .news-title a:hover {{
            color: var(--accent-purple);
        }}

        .original-title {{
            font-size: 0.8rem;
            color: var(--text-muted);
            font-style: italic;
            cursor: help;
            border-bottom: 1px dashed rgba(255, 255, 255, 0.2);
            align-self: flex-start;
            padding-bottom: 1px;
            max-width: 100%;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}

        .news-summary {{
            font-size: 0.95rem;
            line-height: 1.6;
            color: #d1d5db;
        }}
        
        .news-summary.no-summary {{
            color: var(--text-muted);
            font-style: italic;
        }}

        .news-card-footer {{
            margin-top: auto;
            padding-top: 0.5rem;
            border-top: 1px solid rgba(255, 255, 255, 0.04);
        }}

        .read-more-link {{
            color: var(--accent-indigo);
            text-decoration: none;
            font-size: 0.85rem;
            font-weight: 600;
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            transition: color 0.2s;
        }}

        .read-more-link:hover {{
            color: var(--accent-purple);
        }}

        .link-arrow {{
            transition: transform 0.2s;
        }}

        .read-more-link:hover .link-arrow {{
            transform: translate(2px, -2px);
        }}

        .no-news-placeholder {{
            text-align: center;
            color: var(--text-muted);
            display: flex;
            flex-direction: column;
            align-items: center;
            font-size: 1.1rem;
            width: 100%;
            padding: 3rem;
        }}

        footer.main-footer {{
            border-top: 1px solid var(--border-color);
            background: rgba(10, 15, 28, 0.9);
            padding: 2rem 1.5rem;
            margin-top: 4rem;
            backdrop-filter: blur(10px);
        }}

        .footer-content {{
            max-width: 1200px;
            width: 100%;
            margin: 0 auto;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 1rem;
            font-size: 0.85rem;
            color: var(--text-muted);
        }}

        .footer-left {{
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }}

        .footer-right a {{
            color: var(--text-muted);
            text-decoration: none;
            transition: color 0.2s;
            font-weight: 500;
        }}

        .footer-right a:hover {{
            color: var(--accent-purple);
        }}

        /* Responsive design */
        @media (max-width: 768px) {{
            header.main-header {{
                padding: 1.5rem 1rem;
                flex-direction: column;
                align-items: flex-start;
            }}
            .header-actions {{
                width: 100%;
            }}
            .telegram-btn {{
                width: 100%;
                justify-content: center;
            }}
            main.main-content {{
                padding: 1rem;
                gap: 1.5rem;
            }}
            .day-section {{
                grid-template-columns: 1fr;
            }}
            .news-card {{
                padding: 1.5rem;
            }}
        }}
    </style>
</head>
<body>

    <header class="main-header">
        <div class="brand-section">
            <div class="brand-logo-title">
                <div class="brand-logo">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="color: white;">
                        <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"></path>
                        <polyline points="22,6 12,13 2,6"></polyline>
                    </svg>
                </div>
                <h1 class="brand-title">TechDigest</h1>
            </div>
            <p class="brand-subtitle">Rezumatul zilnic al celor mai importante știri din tehnologie, traduse și condensate automat în limba română cu Gemini API.</p>
        </div>
        
        <div class="header-actions">
            <a href="https://t.me/AiciIntroduciCanalulTau" target="_blank" rel="noopener noreferrer" class="telegram-btn" id="telegram-link">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm4.64 6.8c-.15 1.58-.8 5.42-1.13 7.19-.14.75-.42 1-.68 1.03-.58.05-1.02-.38-1.58-.75-.88-.58-1.38-.94-2.23-1.5-.99-.65-.35-1.01.22-1.59.15-.15 2.71-2.48 2.76-2.69.01-.03.01-.14-.07-.2-.08-.06-.19-.04-.27-.02-.12.02-1.96 1.24-5.52 3.64-.52.36-.99.53-1.41.52-.46-.01-1.35-.26-2.01-.48-.81-.27-1.45-.42-1.39-.89.03-.25.38-.51 1.05-.78 4.12-1.79 6.87-2.97 8.24-3.55 3.93-1.66 4.75-1.95 5.28-1.96.12 0 .38.03.55.17.14.12.18.28.2.44z"/>
                </svg>
                Canal Telegram
            </a>
        </div>
    </header>

    <main class="main-content">
        <!-- Selectorul de zi în format tab -->
        <div class="archive-nav-wrapper">
            <nav class="archive-nav">
                {tabs_str}
            </nav>
        </div>

        <!-- Sectiunile de stiri -->
        {sections_str}
    </main>

    <footer class="main-footer">
        <div class="footer-content">
            <div class="footer-left">
                <span>&copy; {an_curent} TechDigest. Generat automat cu 🤖 Gemini &amp; GitHub Actions.</span>
            </div>
            <div class="footer-right">
                <a href="https://github.com" target="_blank" rel="noopener noreferrer">Vezi codul pe GitHub</a>
            </div>
        </div>
    </footer>

    <script>
        function showDay(dateId) {{
            // Ascunde toate secțiunile de știri
            document.querySelectorAll('.day-section').forEach(section => {{
                section.classList.remove('active');
            }});
            
            // Afișează secțiunea corespunzătoare
            const selectedSection = document.getElementById('day-' + dateId);
            if (selectedSection) {{
                selectedSection.classList.add('active');
            }}
            
            // Actualizează clasa activă pe butoane
            document.querySelectorAll('.tab-btn').forEach(btn => {{
                btn.classList.remove('active');
            }});
            
            const selectedTab = document.getElementById('tab-' + dateId);
            if (selectedTab) {{
                selectedTab.classList.add('active');
            }}
        }}
    </script>
</body>
</html>
"""
    try:
        with open(html_file, "w", encoding="utf-8") as f:
            f.write(html_content)
        logging.info("Site-ul static docs/index.html a fost regenerat cu succes.")
    except Exception as e:
        logging.error(f"Eroare la salvarea fișierului html: {e}")

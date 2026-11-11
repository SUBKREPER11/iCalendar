#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generator kalendarza akademickiego (.ics) z planu zajęć PDF.
Obsługuje studia stacjonarne/niestacjonarne w podziale na Tydzień I i II,
uwzględnia odpracowania/zamiany dni, specyficzne daty wykładów oraz podział na grupy (GL01, GL02, itp.).
Działa wieloplatformowo (macOS, Windows, Linux).
"""

import sys
import os
import re
import uuid
import datetime
from pathlib import Path
import argparse
import pdfplumber

CLASS_TYPES = [
    "wykład", "ćwiczenia", "lab", "proj", "seminarium", "lektorat", "warsztaty", "konwersatorium"
]
TYPE_REGEX = re.compile(r"\b(" + "|".join(CLASS_TYPES) + r")\.?\b", re.IGNORECASE)

DAY_NAMES_PL = [
    "Poniedziałek",
    "Wtorek",
    "Środa",
    "Czwartek",
    "Piątek",
    "Sobota",
    "Niedziela"
]

def get_documents_directory() -> Path:
    """
    Zwraca ścieżkę do katalogu Dokumenty użytkownika niezależnie od systemu operacyjnego (Windows/macOS/Linux).
    """
    # Windows
    if sys.platform == "win32":
        try:
            import ctypes.wintypes
            buf = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
            # CSIDL_PERSONAL = 5
            ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf)
            if buf.value:
                p = Path(buf.value)
                p.mkdir(parents=True, exist_ok=True)
                return p
        except Exception:
            pass
        docs = Path.home() / "Documents"
        docs.mkdir(parents=True, exist_ok=True)
        return docs

    # Linux (obsługa XDG user-dirs)
    if sys.platform.startswith("linux"):
        xdg_config = Path.home() / ".config" / "user-dirs.dirs"
        if xdg_config.exists():
            try:
                with open(xdg_config, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.startswith("XDG_DOCUMENTS_DIR="):
                            val = line.split("=", 1)[1].strip().strip("\"'").replace("$HOME", str(Path.home()))
                            p = Path(val)
                            p.mkdir(parents=True, exist_ok=True)
                            return p
            except Exception:
                pass

    # macOS oraz standardowe ścieżki Unix
    for name in ["Documents", "Dokumenty"]:
        p = Path.home() / name
        if p.exists():
            return p

    docs = Path.home() / "Documents"
    docs.mkdir(parents=True, exist_ok=True)
    return docs

def escape_ics_text(text: str) -> str:
    """Escapuje znaki specjalne dla formatu iCalendar (RFC 5545)."""
    if not text:
        return ""
    text = text.replace("\\", "\\\\")
    text = text.replace(";", r"\;")
    text = text.replace(",", r"\,")
    text = text.replace("\r\n", r"\n").replace("\r", r"\n").replace("\n", r"\n")
    return text

def fold_line(line: str) -> str:
    """Zawija wiersz RFC 5545 jeśli przekracza 75 bajtów (z zachowaniem granic znaków UTF-8)."""
    encoded = line.encode("utf-8")
    if len(encoded) <= 75:
        return line
    lines = []
    chunk_limit = 75
    while len(encoded) > chunk_limit:
        split_idx = chunk_limit
        while split_idx > 0 and (encoded[split_idx] & 0xC0) == 0x80:
            split_idx -= 1
        lines.append(encoded[:split_idx].decode("utf-8"))
        encoded = b" " + encoded[split_idx:]
    if encoded:
        lines.append(encoded.decode("utf-8"))
    return "\r\n".join(lines)

def parse_cell(cell_text: str):
    """
    Parsuje treść komórki planu zajęć.
    Zwraca słownik: title, type, teacher, location, specific_dates.
    """
    lines = [l.strip() for l in cell_text.strip().split("\n") if l.strip()]
    if not lines:
        return None
    first_line = lines[0]
    
    # 1. Specyficzne daty (np. "w datach 25.11, 09.12, 13.01, 28.01")
    specific_dates = []
    dates_match = re.search(r"\b(?:w\s+datach|w\s+dniach|daty:?)\s+([0-9.,\s]+)", first_line, re.IGNORECASE)
    if dates_match:
        dates_str = dates_match.group(1)
        found_dates = re.findall(r"(\d{1,2})\.(\d{1,2})", dates_str)
        specific_dates = [(int(d), int(m)) for d, m in found_dates]
        first_line = first_line[:dates_match.start()] + first_line[dates_match.end():]
        first_line = first_line.strip()
    
    # 2. Forma zajęć (wykład, lab, proj, ćwiczenia)
    class_type = ""
    m_type = TYPE_REGEX.search(first_line)
    if m_type:
        class_type = m_type.group(1).lower()
        title = (first_line[:m_type.start()] + first_line[m_type.end():]).strip()
    else:
        title = first_line
    
    title = re.sub(r"[\s\.\-]+$", "", title).strip()
    title = re.sub(r"\s+", " ", title).strip()
    
    # 3. Prowadzący i sala
    teacher = ""
    location = ""
    if len(lines) >= 3:
        teacher = lines[1]
        location = " ".join(lines[2:])
    elif len(lines) == 2:
        if re.search(r"sala|online|audytorium|hala|lab", lines[1], re.IGNORECASE):
            location = lines[1]
        else:
            teacher = lines[1]
            
    return {
        "title": title,
        "type": class_type,
        "teacher": teacher,
        "location": location,
        "specific_dates": specific_dates
    }

def extract_schedule_from_pdf(pdf_path: Path):
    """
    Odczytuje plik PDF z planem zajęć i parsuje jego strukturę.
    """
    if not pdf_path.exists():
        raise FileNotFoundError(f"Plik nie istnieje: {pdf_path}")
        
    with pdfplumber.open(pdf_path) as pdf:
        text_all = "\n".join([p.extract_text() or "" for p in pdf.pages])
        
    # Kierunek studiów i rok/semestr
    study_field = "Plan"
    semester_info = ""
    start_year = datetime.date.today().year
    end_year = start_year + 1

    first_table = pdf.pages[0].extract_table() if pdf.pages else None
    cell_0_0 = first_table[0][0] if (first_table and first_table[0] and first_table[0][0]) else ""
    header_search_text = f"{cell_0_0}\n{text_all}"

    m_field = re.search(r"KIERUNEK:\s*[\r\n]+\s*([^\r\n]+)", header_search_text, re.IGNORECASE)
    if not m_field:
        m_field = re.search(r"KIERUNEK:\s*([^\r\n]+)", header_search_text, re.IGNORECASE)
    if m_field:
        val = m_field.group(1).strip()
        if "tydzień" not in val.lower():
            study_field = val

    # Informacje o roku i semestrze
    m_sem = re.search(r"rok\s+([IVXLCDM\d]+)[,\s]+semestr\s+([IVXLCDM\d]+)", header_search_text, re.IGNORECASE)
    if m_sem:
        semester_info = f"rok_{m_sem.group(1)}_sem_{m_sem.group(2)}"

    # Rok akademicki
    m_yr = re.search(r"(\d{4})/(\d{4})", header_search_text)
    if m_yr:
        start_year = int(m_yr.group(1))
        end_year = int(m_yr.group(2))

        # Wykrywanie odpracowań / zamian dni (np. "W dniu 28.01.2027r. odbędą się zajęcia ze środy I tygodnia zajęć")
        day_map = {
            "poniedział": 0, "wtork": 1, "wtore": 1, "środ": 2, "czwart": 3, "piąt": 4, "sobot": 5, "niedziel": 6
        }
        roman_map = {"I": 1, "II": 2}
        
        date_overrides = {} # date -> (week_type, day_idx)
        override_pattern = r"[Ww]\s*dniu\s*(\d{1,2})\.(\d{1,2})\.(\d{4})r?\.?\s*[a-ząćęłńóśźż]*\s*odbędą się zajęcia z[e]?\s*([a-ząćęłńóśźż]+)\s*([IVX]+)?\s*tygodnia"
        for m in re.finditer(override_pattern, text_all):
            d, mon, y, target_day_str, target_wk_str = m.groups()
            dt = datetime.date(int(y), int(mon), int(d))
            tgt_day = 0
            for k, v in day_map.items():
                if k in target_day_str.lower():
                    tgt_day = v
                    break
            tgt_wk = roman_map.get(target_wk_str, 1) if target_wk_str else 1
            date_overrides[dt] = (tgt_wk, tgt_day)

        # Daty kalendarzowe dla Tygodnia I i II
        calendar_days = [] # (date, week_type, day_idx)
        page_week_mapping = [(0, 1), (1, 2)] if len(pdf.pages) >= 2 else [(0, 1)]
        
        for page_idx, week_num in page_week_mapping:
            table = pdf.pages[page_idx].extract_table()
            if not table:
                continue
            header_cell_text = ""
            for r in range(min(3, len(table))):
                for c in range(len(table[r])):
                    val = table[r][c]
                    if val and ("tydzień" in val.lower() or "-" in val):
                        header_cell_text += "\n" + val
            
            pattern = r"(\d{1,2})(?:\.(\d{1,2}))?\s*-\s*(\d{1,2})\.(\d{1,2})"
            for m in re.finditer(pattern, header_cell_text):
                s_day = int(m.group(1))
                s_mon = int(m.group(2)) if m.group(2) else int(m.group(4))
                e_day = int(m.group(3))
                e_mon = int(m.group(4))
                s_yr = start_year if s_mon >= 9 else end_year
                e_yr = start_year if e_mon >= 9 else end_year
                cur = datetime.date(s_yr, s_mon, s_day)
                end_dt = datetime.date(e_yr, e_mon, e_day)
                while cur <= end_dt:
                    if cur.weekday() < 5:
                        wk_type = week_num
                        d_idx = cur.weekday()
                        if cur in date_overrides:
                            wk_type, d_idx = date_overrides[cur]
                        calendar_days.append((cur, wk_type, d_idx))
                    cur += datetime.timedelta(days=1)
        
        calendar_days.sort(key=lambda x: x[0])

        # Parsowanie siatki zajęć z tabel
        schedules = {1: [], 2: []}
        time_slot_regex = re.compile(r"(\d{1,2})[:.](\d{2})")
        all_groups = set()

        for page_idx, week_num in page_week_mapping:
            page = pdf.pages[page_idx]
            table = page.extract_table()
            if not table:
                continue
                
            group_cols = {}
            for r in range(min(6, len(table))):
                for c in range(2, len(table[r])):
                    val = table[r][c]
                    if val and re.search(r"GL\d+|gr\b", val, re.IGNORECASE):
                        grp = val.strip()
                        group_cols[c] = grp
                        all_groups.add(grp)
            
            if not group_cols:
                group_cols[2] = "Wszyscy"

            day_idx = -1
            for r_idx in range(len(table)):
                row = table[r_idx]
                col1 = row[1] if len(row) > 1 else None
                if col1:
                    times = time_slot_regex.findall(col1)
                    if len(times) >= 2:
                        start_h, start_m = int(times[0][0]), int(times[0][1])
                        end_h, end_m = int(times[-1][0]), int(times[-1][1])
                        if start_h == 8 and start_m == 15:
                            day_idx += 1
                        
                        # Sprawdzenie czy wiersz jest scalony (wykład dla całego roku)
                        first_col = min(group_cols.keys())
                        first_val = row[first_col] if first_col < len(row) else None
                        is_merged_all = True
                        if first_val and first_val.strip():
                            for other_c in group_cols.keys():
                                if other_c != first_col:
                                    other_val = row[other_c] if other_c < len(row) else None
                                    if other_val is not None:
                                        is_merged_all = False
                                        break
                            if is_merged_all:
                                p_cell = parse_cell(first_val)
                                if p_cell:
                                    schedules[week_num].append({
                                        "day_idx": day_idx,
                                        "start": (start_h, start_m),
                                        "end": (end_h, end_m),
                                        "group": "ALL",
                                        **p_cell
                                    })
                                continue
                        
                        # Przetwarzanie poszczególnych kolumn grup
                        for c_idx, grp_name in group_cols.items():
                            cell_val = row[c_idx] if c_idx < len(row) else None
                            if cell_val and cell_val.strip():
                                p_cell = parse_cell(cell_val)
                                if p_cell:
                                    schedules[week_num].append({
                                        "day_idx": day_idx,
                                        "start": (start_h, start_m),
                                        "end": (end_h, end_m),
                                        "group": grp_name,
                                        **p_cell
                                    })

        return {
            "study_field": study_field,
            "semester_info": semester_info,
            "academic_year": f"{start_year}/{end_year}",
            "all_groups": sorted(list(all_groups)),
            "date_overrides": date_overrides,
            "calendar_days": calendar_days,
            "schedules": schedules
        }

def generate_ics_content(schedule_data: dict, target_group: str = None) -> str:
    """
    Tworzy pełną zawartość pliku .ics (RFC 5545) dla zadanej grupy lub wszystkich grup.
    """
    field = schedule_data["study_field"]
    sem = schedule_data["semester_info"]
    cal_name = f"Plan zajęć - {field}"
    if target_group and target_group != "ALL":
        cal_name += f" ({target_group})"
        
    calendar_days = schedule_data["calendar_days"]
    schedules = schedule_data["schedules"]
    
    events = []
    now_utc = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    
    for cur_date, wk_type, d_idx in calendar_days:
        for item in schedules.get(wk_type, []):
            if item["day_idx"] == d_idx:
                # Filtr grupy
                if target_group and target_group != "ALL":
                    if item["group"] != "ALL" and item["group"] != target_group:
                        continue
                
                # Filtr specyficznych dat
                if item["specific_dates"]:
                    if (cur_date.day, cur_date.month) not in item["specific_dates"]:
                        continue
                
                start_dt = datetime.datetime(
                    cur_date.year, cur_date.month, cur_date.day,
                    item["start"][0], item["start"][1]
                )
                end_dt = datetime.datetime(
                    cur_date.year, cur_date.month, cur_date.day,
                    item["end"][0], item["end"][1]
                )
                
                # Przygotowanie pól wydarzenia
                type_suffix = f" ({item['type']})" if item['type'] else ""
                summary = f"{item['title']}{type_suffix}"
                
                desc_parts = []
                if item["type"]:
                    desc_parts.append(f"Forma: {item['type']}")
                if item["teacher"]:
                    desc_parts.append(f"Prowadzący: {item['teacher']}")
                if item["group"] != "ALL":
                    desc_parts.append(f"Grupa: {item['group']}")
                else:
                    desc_parts.append("Grupa: Cały rok")
                if item["location"]:
                    desc_parts.append(f"Miejsce: {item['location']}")
                
                description = "\n".join(desc_parts)
                location = item["location"]
                
                uid = f"{cur_date.strftime('%Y%m%d')}_{start_dt.strftime('%H%M')}_{uuid.uuid5(uuid.NAMESPACE_DNS, summary + item['group'])}@academic.schedule"
                
                events.append({
                    "uid": uid,
                    "dtstamp": now_utc,
                    "dtstart": start_dt.strftime("%Y%m%dT%H%M%S"),
                    "dtend": end_dt.strftime("%Y%m%dT%H%M%S"),
                    "summary": escape_ics_text(summary),
                    "description": escape_ics_text(description),
                    "location": escape_ics_text(location)
                })

    # Składanie pliku ICS
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Academic Schedule PDF to ICS//PL",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{cal_name}",
        "X-WR-TIMEZONE:Europe/Warsaw",
        "BEGIN:VTIMEZONE",
        "TZID:Europe/Warsaw",
        "X-LIC-LOCATION:Europe/Warsaw",
        "BEGIN:DAYLIGHT",
        "TZOFFSETFROM:+0100",
        "TZOFFSETTO:+0200",
        "TZNAME:CEST",
        "DTSTART:19700329T020000",
        "RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU",
        "END:DAYLIGHT",
        "BEGIN:STANDARD",
        "TZOFFSETFROM:+0200",
        "TZOFFSETTO:+0100",
        "TZNAME:CET",
        "DTSTART:19701025T030000",
        "RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU",
        "END:STANDARD",
        "END:VTIMEZONE"
    ]
    
    for ev in events:
        lines.append("BEGIN:VEVENT")
        lines.append(f"UID:{ev['uid']}")
        lines.append(f"DTSTAMP:{ev['dtstamp']}")
        lines.append(f"DTSTART;TZID=Europe/Warsaw:{ev['dtstart']}")
        lines.append(f"DTEND;TZID=Europe/Warsaw:{ev['dtend']}")
        lines.append(f"SUMMARY:{ev['summary']}")
        if ev["description"]:
            lines.append(f"DESCRIPTION:{ev['description']}")
        if ev["location"]:
            lines.append(f"LOCATION:{ev['location']}")
        lines.append("STATUS:CONFIRMED")
        lines.append("END:VEVENT")
        
    lines.append("END:VCALENDAR")
    
    folded_lines = [fold_line(l) for l in lines]
    return "\r\n".join(folded_lines) + "\r\n", len(events)

def sanitize_filename(name: str) -> str:
    """Czyści nazwę pliku z niedozwolonych znaków w systemach plików."""
    return re.sub(r'[\\/*?:"<>| ]', "_", name).strip("_")

def main():
    parser = argparse.ArgumentParser(
        description="Konwertuje plan zajęć ze studiów w formacie PDF na plik kalendarza iCalendar (.ics) zapisywany w Dokumentach."
    )
    parser.add_argument("pdf_path", help="Ścieżka do pliku PDF z planem zajęć")
    parser.add_argument("-g", "--group", help="Grupa studencka (np. GL01, GL02 lub 'all' / 'wszystkie')", default=None)
    parser.add_argument("-o", "--output", help="Opcjonalny niestandardowy katalog zapisu lub nazwa pliku", default=None)
    
    args = parser.parse_args()
    
    raw_pdf_path = Path(args.pdf_path).expanduser().resolve()
    if not raw_pdf_path.exists():
        print(f"BŁĄD: Plik PDF '{args.pdf_path}' nie został znaleziony.")
        sys.exit(1)
        
    print(f"Odczytuję plan z: {raw_pdf_path}")
    try:
        schedule_data = extract_schedule_from_pdf(raw_pdf_path)
    except Exception as e:
        print(f"BŁĄD podczas analizy PDF: {e}")
        sys.exit(1)
        
    all_groups = schedule_data["all_groups"]
    print(f"Kierunek: {schedule_data['study_field']}")
    print(f"Rok akademicki: {schedule_data['academic_year']}")
    print(f"Liczba dni zajęciowych w semestrze: {len(schedule_data['calendar_days'])}")
    if schedule_data["date_overrides"]:
        print(f"Wykryte zamiany/odpracowania dni: {len(schedule_data['date_overrides'])}")
        for ov_date, (ov_wk, ov_d) in schedule_data["date_overrides"].items():
            print(f"  - {ov_date}: realizacja planu dla {DAY_NAMES_PL[ov_d]} (Tydzień {ov_wk})")

    # Wybór grupy
    selected_groups = []
    if args.group:
        grp = args.group.strip()
        if grp.lower() in ["all", "wszystkie", "obie"]:
            selected_groups = all_groups if all_groups else ["ALL"]
        else:
            selected_groups = [grp]
    elif all_groups:
        if len(all_groups) == 1:
            selected_groups = all_groups
        elif sys.stdin.isatty():
            print("\nWykryto grupy studenckie w planie:")
            for i, g in enumerate(all_groups, 1):
                print(f"  {i}) {g}")
            print(f"  {len(all_groups) + 1}) Wszystkie grupy (osobne pliki .ics)")
            print(f"  {len(all_groups) + 2}) Wszystkie grupy (jeden wspólny plik .ics)")
            choice = input(f"Wybierz opcję [1-{len(all_groups) + 2}] (domyślnie {len(all_groups) + 1}): ").strip()
            if not choice or choice == str(len(all_groups) + 1):
                selected_groups = all_groups
            elif choice == str(len(all_groups) + 2):
                selected_groups = ["ALL"]
            else:
                try:
                    idx = int(choice) - 1
                    if 0 <= idx < len(all_groups):
                        selected_groups = [all_groups[idx]]
                    else:
                        selected_groups = all_groups
                except ValueError:
                    selected_groups = all_groups
        else:
            # Tryb nieinteraktywny - twórz dla każdej grupy osobny plik
            selected_groups = all_groups
    else:
        selected_groups = ["ALL"]

    # Określenie katalogu docelowego
    if args.output:
        out_target = Path(args.output).expanduser().resolve()
        if out_target.is_dir():
            target_dir = out_target
            custom_filename = None
        else:
            target_dir = out_target.parent
            custom_filename = out_target.name
    else:
        target_dir = get_documents_directory()
        custom_filename = None

    target_dir.mkdir(parents=True, exist_ok=True)
    field_slug = sanitize_filename(schedule_data["study_field"])
    sem_slug = sanitize_filename(schedule_data["semester_info"])

    print(f"\nZapisywanie kalendarza do: {target_dir}")
    
    for grp in selected_groups:
        ics_text, count = generate_ics_content(schedule_data, target_group=grp)
        if custom_filename and len(selected_groups) == 1:
            file_name = custom_filename if custom_filename.endswith(".ics") else f"{custom_filename}.ics"
        else:
            file_name = f"Plan_{field_slug}"
            if sem_slug:
                file_name += f"_{sem_slug}"
            if grp and grp != "ALL":
                file_name += f"_{grp}"
            file_name += ".ics"
            
        out_path = target_dir / file_name
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(ics_text)
            
        print(f" -> Wygenerowano: {out_path} ({count} wydarzeń)")

    print("\nZakończono sukcesem! Pliki .ics można zaimportować do Kalendarza Apple, Google, Outlook, itp.")

if __name__ == "__main__":
    main()

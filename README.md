# 📅 Academic Schedule PDF to iCalendar (.ics)

[![Python Version](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Windows%20%7C%20Linux-lightgrey.svg)]()
[![Format](https://img.shields.io/badge/format-RFC%205545%20(iCalendar)-green.svg)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Narzędzie w języku Python do automatycznej konwersji uczelnianych planów zajęć w formacie PDF na pliki kalendarza **`.ics`** (iCalendar zgodne z **RFC 5545**). 

Wygenerowany plik kalendarza można natychmiast zaimportować do:
- **Apple Calendar** (macOS, iOS)
- **Google Calendar** (Android, Web)
- **Microsoft Outlook**
- **Mozilla Thunderbird**

Program automatycznie zapisuje gotowe pliki w systemowym katalogu **Dokumenty** użytkownika, niezależnie od używanego systemu operacyjnego.

---

## 🚀 Główne funkcjonalności

- 🖥️ **Pełna wieloplatformowość**:
  - Działa na **macOS**, **Windows** oraz **Linux**.
  - Automatycznie wykrywa lokalizację katalogu `Dokumenty` (w tym API Windows Shell `CSIDL_PERSONAL` oraz `XDG_DOCUMENTS_DIR` na Linuksie).
- 📆 **Obsługa cyklu dwutygodniowego (Tydzień I / Tydzień II)**:
  - Automatycznie odczytuje zakresy dat dla Tygodnia I i Tygodnia II z nagłówka planu.
  - Generuje wydarzenia dla każdego dnia zajęć przez cały semestr (np. 15 tygodni / 75 dni roboczych).
- 🔄 **Wykrywanie odpracowań i zamian dni**:
  - Automatycznie parsuje adnotacje z dołu strony, np.:
    > *„W dniu 28.01.2027r. czwartek odbędą się zajęcia ze środy I tygodnia zajęć”*
  - Podstawia w tym dniu plan ze wskazanego dnia tygodnia.
- 🎯 **Wykłady o dedykowanych terminach**:
  - Obsługuje przedmioty odbywające się wyłącznie w wyznaczonych datach, np.:
    > *„KOMPUTEROWE WSPOMAGANIE PROJEKTOWANIA wykład w datach 25.11, 09.12, 13.01, 28.01”*
  - Nie zaśmieca kalendarza – zajęcia pojawiają się wyłącznie w dniach, kiedy faktycznie się odbywają.
- 👥 **Podział na grupy studenckie (`GL01`, `GL02`, itp.)**:
  - Wykrywa kolumny grup w siatce zajęć.
  - Wspólne wykłady (komórki scalone na cały rok) są automatycznie uwzględniane w planie każdej grupy.
  - Pozwala wybrać grupę przez flagę CLI lub w interaktywnym menu w konsoli.
- ⏰ **Zgodność ze standardem RFC 5545**:
  - Posiada pełną definicję strefy czasowej `Europe/Warsaw` (`VTIMEZONE`) z uwzględnieniem czasu letniego i zimowego.
  - Generuje deterministyczne identyfikatory `UID`, nazwy przedmiotów z formą zajęć w tytule, prowadzącego, salę oraz tryb online.
  - Zapewnia prawidłowe zawijanie długich wierszy (do 75 bajtów) z zachowaniem integralności znaków UTF-8.

---

## 📦 Wymagania i instalacja

Wymagany jest **Python 3.9+**.

1. Sklonuj repozytorium:
   ```bash
   git clone https://github.com/twoj-login/twoje-repo.git
   cd twoje-repo
   ```

2. Utwórz i aktywuj środowisko wirtualne:
   - **macOS / Linux**:
     ```bash
     python3 -m venv .venv
     source .venv/bin/activate
     ```
   - **Windows** (Command Prompt / PowerShell):
     ```cmd
     python -m venv .venv
     .venv\Scripts\activate
     ```

3. Zainstaluj zależności:
   ```bash
   pip install -r requirements.txt
   ```

---

## 💻 Sposób użycia

### 1. Podstawowe wywołanie
Wystarczy podać ścieżkę do pliku PDF z planem:
```bash
python pdf_to_ics.py /sciezka/do/INFORMATYKA-2.pdf
```
Jeśli plan zawiera więcej niż jedną grupę, program wyświetli w konsoli menu wyboru:
```text
Wykryto grupy studenckie w planie:
  1) GL01
  2) GL02
  3) Wszystkie grupy (osobne pliki .ics)
  4) Wszystkie grupy (jeden wspólny plik .ics)
Wybierz opcję [1-4] (domyślnie 3):
```

### 2. Wybór grupy z poziomu argumentów
Możesz podać grupę bezpośrednio za pomocą flagi `-g` / `--group`:
```bash
# Wygeneruj plan tylko dla grupy GL01
python pdf_to_ics.py /sciezka/do/INFORMATYKA-2.pdf -g GL01

# Wygeneruj pliki dla wszystkich grup naraz
python pdf_to_ics.py /sciezka/do/INFORMATYKA-2.pdf -g all
```

### 3. Wskazanie własnego folderu lub nazwy pliku
Domyślnie pliki zapisywane są w systemowym folderze **Dokumenty**. Aby zapisać je w innym miejscu, użyj flagi `-o` / `--output`:
```bash
# Zapis w wybranym katalogu
python pdf_to_ics.py /sciezka/do/INFORMATYKA-2.pdf -o ./kalendarze

# Zapis pod konkretną nazwą pliku
python pdf_to_ics.py /sciezka/do/INFORMATYKA-2.pdf -g GL01 -o moj_plan.ics
```

---

## ⚙️ Opcje wiersza poleceń

| Argument | Flaga | Domyślnie | Opis |
| :--- | :--- | :--- | :--- |
| `pdf_path` | *(pozycyjny)* | **wymagany** | Ścieżka do pliku PDF z planem zajęć. |
| `--group` | `-g` | `None` | Grupa studencka (np. `GL01`, `GL02`, `all` / `wszystkie`). |
| `--output` | `-o` | Katalog Dokumentów | Ścieżka wyjściowa (katalog lub nazwa pliku `.ics`). |
| `--help` | `-h` | — | Wyświetla pomoc i listę dostępnych opcji. |

---

## 📂 Przykładowe wygenerowane pliki

Pliki kalendarza tworzone są z intuicyjnymi nazwami uwzględniającymi kierunek, semestr i grupę:
- `Plan_informatyka_rok_II_sem_III_GL01.ics`
- `Plan_informatyka_rok_II_sem_III_GL02.ics`

---

## 📁 Struktura projektu

```text
.
├── pdf_to_ics.py       # Główny skrypt konwertujący
├── requirements.txt    # Zależności biblioteczne (pdfplumber)
├── .gitignore          # Reguły ignorowania plików dla gita
└── README.md           # Dokumentacja projektu
```

---

## 📄 Licencja

Projekt udostępniany na licencji MIT.

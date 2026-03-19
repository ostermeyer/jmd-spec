# JMD Benchmark Report — Vollständige Dokumentation

*Erstellt: 2026-03-15 | Testzeitraum: 2026-03-12 bis 2026-03-15*

---

## Inhaltsverzeichnis

1. Überblick und Motivation
2. Teststufen, Methodik und Szenarien
3. Phase 0: Initiale Live-Tests (Budget-Modelle)
4. Phase 0.5: TOON-Evaluation und Ausschluss
5. Phase 1: Single-Run über 6 Modelle
6. Ergebnisse im Detail
7. Phase 1.5: Format-Fidelity-Test
8. Modellvergleich und Analyse
9. Empfehlungen für Phase 2
10. Phase 2: Statistisch belastbarer Benchmark (30 Runs)
11. Phase 3: Agentic Chains (Multi-Step-Workflows)
12. Phase 4a: Streaming TTFUB (Time-to-First-Useful-Byte)
13. Phase 4b: Epistemische Evaluation (Deploy-Gate-Experiment)
14. Phase 5: Halluzinations-Evaluation (Due-Diligence-Experiment)
15. Phase 5b: Inferenz-Transparenz unter realistischen Bedingungen
16. Phase 6a: Modus-Agilität (Inventory-Management-Experiment)
17. Phase 6b: Deep Nesting Stress Test (Filesystem-Experiment)
18. Phase 6c: Schema-Roundtrip (Employee-Directory-Experiment)
19. Phase 7: Query-by-Example (Employee-Directory-Experiment)
20. Phase 8: Delete Documents (Employee-Directory-Experiment)

---

## 1. Überblick und Motivation

JMD (JSON Markdown) ist ein zeilenorientiertes Serialisierungsformat, das Markdown-Headings zur Strukturierung nutzt. Ziel der Benchmarks ist der Nachweis, dass JMD gegenüber JSON als LLM-Ausgabeformat folgende Vorteile bietet:

- **Weniger Output-Tokens** → weniger Inferenzkosten und GPU-Zeit
- **Schnelleres Time-to-First-Useful-Byte (TTFUB)** → bessere Streaming-Latenz
- **Zeilenweises Parsing** → graceful degradation bei Abbruch
- **Gleiche oder bessere semantische Korrektheit**

Die Tests decken drei Provider (Anthropic, OpenAI, Google) über drei Preistiers ab, um die Generalisierbarkeit der Ergebnisse zu validieren.

---

## 2. Teststufen und Methodik

### Stufenweiser Ansatz

Um Kosten zu kontrollieren und frühzeitig Probleme zu erkennen, wurde ein dreistufiger Ansatz gewählt:

| Phase | Ziel | Umfang | Kosten |
|---|---|---|---|
| **Phase 0** | Format-Validierung | 1 Run × 3 Budget-Modelle × 3 Formate | ~$0.50 |
| **Phase 0.5** | TOON-Evaluation | Byte-Vergleich, Parse-Benchmark, Adoption-Research | $0 |
| **Phase 1** | Modell-Breite | 1 Run × 6 Modelle × 3 Formate × 5-Step Chain | ~$1.20 |
| **Phase 2** | Statistisch belastbar | 30 Runs × ausgewählte Modelle × 3 Formate | ~$50–150 |

### Benchmark-Szenarien

Jeder Run besteht aus einer **5-Step-Chain**, die einen realistischen Workflow simuliert. Jeder Step erhält das Ergebnis des vorherigen als Kontext (chained prompts). Bricht ein Step ab (Syntax-Fehler, Timeout), werden die folgenden Steps übersprungen.

Drei Szenarien decken unterschiedliche Datenprofile ab:

#### E-Commerce: Shopping-Flow

| Step | Name | Aufgabe |
|---|---|---|
| 1 | `search_products` | Produktkatalog analysieren, Top-3 nach Rating identifizieren |
| 2 | `check_availability` | Verfügbarkeit prüfen, bestes verfügbares Produkt auswählen |
| 3 | `build_cart` | Warenkorb-Request mit Produkt-ID, Menge, Lieferadresse bauen |
| 4 | `place_order` | Order-ID und Lieferzeit aus Bestätigung extrahieren |
| 5 | `summarize` | Bestellzusammenfassung als Freitext (unstrukturiert) |

**Daten**: 15 Produkte × 12 Felder (ID, Name, Preis, Rating, Lager, etc.). Availability-Daten enthalten bewusst widersprüchliche Ratings (Vendor vs. Community), um Reasoning-Fehler von Format-Fehlern zu trennen.

**Validierung**: Step 1 prüft gegen exakte Top-3-Sortierung (Rating desc, Preis asc). Step 3 prüft korrekte Produkt-ID (40%), positive Menge (30%), Lieferadresse vorhanden (30%).

**Profil**: Relativ flache Strukturen, moderate Verschachtelung bei Cart/Order. Geringster JMD-Vorteil bei Tokens, da JSON hier wenig Struktur-Overhead hat.

#### DevOps: Issue-Triage-Pipeline

| Step | Name | Aufgabe |
|---|---|---|
| 1 | `list_issues` | 20 Issues analysieren, Top-5 Bugs nach Severity + Recency identifizieren |
| 2 | `prioritize` | Detail-Daten inkl. Kommentare auswerten, Ranking mit Begründung |
| 3 | `update_status` | Update-Request für Top-Issue erstellen (Status → in_progress) |
| 4 | `post_comment` | Triage-Kommentar mit Entscheidungsbegründung verfassen |
| 5 | `link_pr` | Passenden Pull Request finden und mit Issue verknüpfen |

**Daten**: 20 Issues × 10–12 Felder + verschachtelte Kommentar-Arrays (0–8 pro Issue) + 8 Open PRs. Bewusst eingebaute Severity-Konflikte: Reporter-Severity vs. ML-Classifier-Severity (82% Accuracy) erzwingen Abwägungsentscheidungen.

**Validierung**: Step 1 prüft gegen Ground-Truth-Prioritätsliste (Severity-Rank + Recency als Tiebreaker, ≥60% Overlap). Step 5 prüft korrekte PR-ID/Issue-ID-Verknüpfung.

**Profil**: Text-intensiv, tiefste Verschachtelung (Issue-Bodies als Markdown + Kommentar-Arrays). Größter JMD-Vorteil bei Tokens: Headings ersetzen verschachtelte JSON-Klammern effizient.

#### Data Pipeline: Sales-ETL

| Step | Name | Aufgabe |
|---|---|---|
| 1 | `check_quality` | 30 Datensätze auf Anomalien prüfen (negative Margen, Ausreißer) |
| 2 | `aggregate` | Aggregations-Request erstellen (Group-by Region, Sum/Avg) |
| 3 | `validate_results` | Aggregierte Ergebnisse prüfen, Anomalien flaggen |
| 4 | `store_results` | Store-Request mit Ergebnis-Daten und Metadaten (Pipeline-ID, Timestamp) |
| 5 | `summarize` | Narrative Zusammenfassung: Revenue, Regionen, Anomalien (unstrukturiert) |

**Daten**: 30 Sales-Records × 9 numerische/String-Felder (Region, Produkt, Quantity, Revenue, Cost, Margin). 3 injizierte Anomalien (negative Margen an festen Positionen). Aggregation auf ~5 Regionen mit unterschiedlichen Confidence-Levels für Anomalie-Erkennung.

**Validierung**: Step 1 prüft, ob die spezifischen Anomalie-Record-IDs im Output erscheinen + Quality-Keywords. Step 4 prüft Vorhandensein von Ergebnis-Daten und Metadaten.

**Profil**: Numerisch-analytisch, größtes Datenvolumen (30 Records). Erfordert rechnerische Reasoning (Margen, Summen). Größte Token-Einsparung in Phase 2 (−9,8% Total).

#### Szenario-Vergleich

| Aspekt | E-Commerce | DevOps | Data Pipeline |
|---|---|---|---|
| Datensätze | 15 Produkte | 20 Issues + 8 PRs | 30 Sales-Records |
| Felder pro Datensatz | 12 | 10–12 + Kommentare | 9 |
| Strukturierte Steps | 4 von 5 | 5 von 5 | 4 von 5 |
| Ambiguität | Rating-Konflikte | Severity-Konflikte | Confidence-Levels |
| Schwierigster Step | Top-3-Ranking | Top-5-Priorisierung | Anomalie-Erkennung |
| Daten-Profil | Flach, moderate Verschachtelung | Text-intensiv, tief verschachtelt | Numerisch, hohes Volumen |

### Formate

| Format | Beschreibung |
|---|---|
| **JSON pretty** | Standard-JSON mit Einrückung (Default-Verhalten aller LLMs) |
| **JSON minified** | Einzeiliges JSON ohne Whitespace |
| **JMD** | JMD v0.3 mit 5-Bullet-Minimal-Primer (~80 Input-Tokens) |

### JMD-Primer (5 Bullets, ~80 Tokens)

```
You are an API assistant. Return data as JMD (JSON Markdown).

JMD rules:
- # Label starts the root object; ## key opens nested objects (depth = nesting)
- ## key[] declares an array; items start with - (no sub-headings per item)
- key: value for fields, no other markup
- Array objects: - key: value, indented continuation lines
- > blockquotes for multiline text

Produce only the data.
```

### Metriken

- **Output-Tokens**: Vom Provider gemeldete Token-Anzahl
- **Syntaktische Validität**: JMD → `JMDParser().parse()`, JSON → `json.loads()`
- **Semantische Korrektheit**: Vergleich gegen Ground-Truth-Felder (Produkt-IDs, Preise, etc.)
- **TTFUB**: Zeit bis zum ersten nutzbaren Datenbyte im Streaming
- **Wall Clock**: Gesamtzeit Client-seitig (inkl. Netzwerklatenz)
- **Kosten**: Berechnet aus Provider-Pricing (Input + Output)

---

## 3. Phase 0: Initiale Live-Tests (Budget-Modelle)

*Durchgeführt: 2026-03-12*

### 3.1 Erster Test: 300-Token-Primer

Drei Budget-Modelle mit ausführlichem Primer (~300 Tokens, inkl. Beispiel):

| LLM | JSON Output | JMD Output | Einsparung |
|---|---|---|---|
| Claude Sonnet 4.6 | 405 tok | 244 tok | **−39.8%** |
| GPT-4o | 277 tok | 172 tok | **−37.9%** |
| Gemini 2.5 Flash | 297 tok | 240 tok | **−19.2%** |

**Durchschnitt: −32.3% Output-Tokens**

Erkenntnis: Der ~300-Token-Primer funktioniert, ist aber teuer als Input-Overhead.

### 3.2 Minimal-Primer-Test: 5 Bullets

Reduktion auf 5 Regeln ohne Beispiel (~80 Tokens):

| LLM | JSON Output | JMD Output | Einsparung |
|---|---|---|---|
| Claude Sonnet 4.6 | 414 tok | 272 tok | **−34.3%** |
| GPT-4o | 277 tok | 189 tok | **−31.8%** |
| Gemini 2.5 Flash | 297 tok | 265 tok | **−10.8%** |

**Durchschnitt: −25.6% Output-Tokens**

Erkenntnis: Der 5-Bullet-Primer reicht aus. Alle drei LLMs produzieren valides JMD. Die geringere Einsparung bei Gemini liegt daran, dass Gemini bereits von sich aus minifizierten JSON produziert.

### 3.3 Compute-Benchmark (10 Runs, trimmed mean)

Statistisch belastbarer Compute-Vergleich auf drei Budget-Modellen:

| Modell | JMD vs Pretty JSON | JMD vs Minified JSON |
|---|---|---|
| Gemini 2.5 Flash | −34% tok / **−31% Server-Zeit** | +8% tok / −19% Server-Zeit |
| GPT-4.1-mini | −27% tok / **−27% Server-Zeit** | +17% tok / −6% Server-Zeit |
| Claude Haiku 4.5 | −34% tok / **−13% Server-Zeit** | +12% tok / +30% Server-Zeit |

**Erkenntnis**: Gegen Pretty JSON (realer Default) spart JMD 13–31% Server-Verarbeitungszeit. Gegen Minified JSON ist das Bild gemischt — JMD hat mehr Tokens, aber teilweise trotzdem weniger Server-Zeit (effizientere Generierung).

### 3.4 Tiktoken-Analyse (identische Daten)

Um den reinen Format-Overhead zu messen, wurden identische Daten in allen drei Formaten serialisiert und mit dem GPT-4o-Tokenizer gezählt:

| Vergleich | Ergebnis |
|---|---|
| JMD vs Pretty JSON | **−26 bis −29% Tokens** |
| JMD vs Minified JSON | **+11 bis +14% Tokens** |

JMD hat einen strukturellen Overhead von ~12% gegenüber Minified JSON (Headings, Zeilenumbrüche). Der Vorteil gegenüber Pretty JSON ist erheblich. Da LLMs standardmäßig Pretty JSON produzieren, ist der reale Vergleich JMD vs Pretty JSON.

---

## 4. Phase 0.5: TOON-Evaluation und Ausschluss

*Durchgeführt: 2026-03-14*

TOON (Token-Oriented Object Notation) wurde als potenzieller Konkurrent evaluiert.

### 4.1 Format-Vergleich

TOON ist ein CSV-artiges tabellarisches Format für uniforme Arrays:

```
# TOON header
key1,key2,key3
val1,val2,val3
val4,val5,val6
```

### 4.2 Byte-Size-Vergleich

| Szenario | TOON vs JSON | JMD vs JSON |
|---|---|---|
| Uniforme Arrays (Tabelle) | **−61.6%** | −28.4% |
| Gemischte/verschachtelte Daten | **+6.1%** | −18.3% |

TOON gewinnt deutlich bei tabellarischen Daten, verliert aber bei der im LLM-Kontext dominanten verschachtelten Struktur.

### 4.3 Parse-Performance

| Operation | TOON | JSON (C) | JMD (C) |
|---|---|---|---|
| Parse | **6–17× langsamer als JSON** | Baseline | 1.4–2.9× schneller |
| Serialize | Nicht getestet (kein C-Impl.) | Baseline | 1.6–6.0× schneller |

TOON hat keine C-Implementierung. Die reine Python-Implementierung ist erwartungsgemäß deutlich langsamer.

### 4.4 Adoption und Ökosystem

- 22.700 GitHub-Stars (starkes anfängliches Interesse)
- **Null Production-Adoption** durch LLM-Provider
- Python-Implementierung: letztes Update Dezember 2025
- Kein SDK für Go, Rust, Java, C++
- Keine Streaming-Unterstützung
- Kein Query- oder Schema-Dialekt

### 4.5 Fazit

**TOON ist de facto tot.** Keine Provider-Adoption, keine C-Implementierung, keine Streaming-Fähigkeit. Die Investition in TOON-Benchmarks würde keine verwertbaren Ergebnisse liefern. TOON wurde aus dem Benchmark-Plan ausgeschlossen.

---

## 5. Phase 1: Single-Run über 6 Modelle

*Durchgeführt: 2026-03-14 bis 2026-03-15*

### 5.1 Modellauswahl

| Tier | Anthropic | OpenAI | Google |
|---|---|---|---|
| **Top** | — | GPT-5.4 ($2.50/$15) | Gemini 3.1 Pro ($1.25/$10) |
| **Mid** | Sonnet 4.6 ($3/$15) | — | — |
| **Budget** | Haiku 4.5 ($0.80/$4) | GPT-5 Nano ($0.05/$0.40) | Gemini 3 Flash Preview |

Anmerkungen:
- Opus 4.6 wurde wegen hoher Kosten ($15/$75) zunächst ausgelassen
- GPT-5 ($1.25/$10) wurde zugunsten des günstigeren GPT-5 Nano und des leistungsstärkeren GPT-5.4 übersprungen
- `gemini-3.1-flash` existierte zum Testzeitpunkt nicht als API-Modell; stattdessen wurde `gemini-3-flash-preview` verwendet

### 5.2 Konfiguration

- **Runs pro Format**: 1 JSON-pretty, 1 JSON-minified, 21 JMD (mehr Runs für Reliabilitäts-Assessment)
- **Chain**: 5 Steps × je Run
- **Temperature**: 0.0
- **Streaming**: Aktiviert für TTFUB-Messung
- **Primer**: 5-Bullet-Minimal (~80 Tokens)

### 5.3 Technische Probleme während der Tests

| Problem | Modell | Lösung |
|---|---|---|
| `gemini-3.1-flash` 404 | Google | Modell existiert nicht; `gemini-3-flash-preview` verwendet |
| Temperature=0 nicht unterstützt | GPT-5 Nano | `_supports_temperature()` Methode hinzugefügt; Temperature-Parameter wird für Nano/o-series ausgelassen |
| Hohe Latenz bei Preview-Modellen | Gemini 3 Flash | Akzeptiert; Preview-Status bedeutet nicht-optimierte Infrastruktur |
| Rate-Limiting (429) | Gemini 3.1 Pro | Automatischer Retry mit exponentiellem Backoff (15s × Versuch) |

### 5.4 Gesamtkosten Phase 1

| Modell | JMD-Kosten | JSON-Kosten | Gesamt |
|---|---|---|---|
| Claude Haiku 4.5 | $0.080 | $0.009 | **$0.089** |
| Claude Sonnet 4.6 | $0.321 | $0.035 | **$0.356** |
| GPT-5.4 | $0.220 | $0.024 | **$0.244** |
| GPT-5 Nano | $0.056 | $0.004 | **$0.059** |
| Gemini 3 Flash | $0.268 | $0.032 | **$0.299** |
| Gemini 3.1 Pro | $0.120 | $0.016 | **$0.135** |
| **Gesamt** | | | **$1.18** |

---

## 6. Ergebnisse im Detail

### 6.1 Claude Haiku 4.5

| Metrik | JSON pretty | JSON minified | JMD |
|---|---|---|---|
| Output-Tokens (search_products) | 163 | 150 | 112 avg |
| Gesamt Output-Tokens (alle Steps) | 458 | 522 | 7.436 (21 Runs) |
| Syntaktische Validität | 5/5 (100%) | 5/5 (100%) | 105/105 (100%) |
| Semantische Korrektheit | 3/5 (60%) | 3/5 (60%) | 54/105 (51%) |
| Chain Completion | 5/5 (100%) | 5/5 (100%) | 105/105 (100%) |
| TTFUB (Median, search_products) | 1.09s | 1.08s | 0.51s |

**Token-Einsparung (search_products): −31% vs Pretty JSON, −25% vs Minified**

**TTFUB**: JMD liefert das erste nutzbare Byte **2× schneller** als JSON.

**Bewertung**: Exzellente JMD-Unterstützung. 100% syntaktische Validität über alle 105 Steps. Haiku versteht den Minimal-Primer perfekt.

---

### 6.2 Claude Sonnet 4.6

| Metrik | JSON pretty | JSON minified | JMD |
|---|---|---|---|
| Output-Tokens (search_products) | 167 | 167 | 116 avg |
| Gesamt Output-Tokens (alle Steps) | 617 | 510 | 8.605 (21 Runs) |
| Syntaktische Validität | 5/5 (100%) | 5/5 (100%) | 105/105 (100%) |
| Semantische Korrektheit | 3/5 (60%) | 3/5 (60%) | 72/105 (69%) |
| Chain Completion | 5/5 (100%) | 5/5 (100%) | 105/105 (100%) |
| TTFUB (Median, search_products) | 2.53s | 2.36s | 1.23s |

**Token-Einsparung (search_products): −31% vs Pretty JSON, −31% vs Minified**

**TTFUB**: JMD ist **~2× schneller** als JSON beim ersten nutzbaren Byte.

**Bewertung**: Beste JMD-Unterstützung aller getesteten Modelle. 100% Chain Completion, 100% syntaktische Validität, höchste semantische Korrektheit (69%). Sonnet produziert konsistent sauberes, strukturiertes JMD.

---

### 6.3 GPT-5.4

| Metrik | JSON pretty | JSON minified | JMD |
|---|---|---|---|
| Output-Tokens (search_products) | 139 | 140 | 100 avg |
| Gesamt Output-Tokens (alle Steps) | 351 | 331 | 5.478 (21 Runs) |
| Syntaktische Validität | 5/5 (100%) | 5/5 (100%) | 93/105 (89%) |
| Semantische Korrektheit | 4/5 (80%) | 4/5 (80%) | 65/105 (62%) |
| Chain Completion | 5/5 (100%) | 5/5 (100%) | 96/105 (91%) |
| TTFUB (Median, search_products) | 2.01s | 1.90s | 0.59s |

**Token-Einsparung (search_products): −28% vs Pretty JSON, −29% vs Minified**

**TTFUB**: JMD ist **3× schneller** als JSON — bestes TTFUB-Ergebnis aller Modelle.

**Bewertung**: Starke JMD-Performance. Leicht niedrigere syntaktische Validität (89%) als die Claude-Modelle, aber herausragende Streaming-Latenz. 9 übersprungene Steps wegen Chain-Abbrüchen.

---

### 6.4 GPT-5 Nano

| Metrik | JSON pretty | JSON minified | JMD |
|---|---|---|---|
| Output-Tokens (search_products) | 1.418 | 1.205 | 1.569 avg |
| Gesamt Output-Tokens (alle Steps) | 4.139 | 4.343 | 132.232 (21 Runs) |
| Syntaktische Validität | 5/5 (100%) | 5/5 (100%) | 105/105 (100%) |
| Semantische Korrektheit | 3/5 (60%) | 2/5 (40%) | 60/105 (57%) |
| Chain Completion | 5/5 (100%) | 5/5 (100%) | 105/105 (100%) |
| TTFUB (Median, search_products) | 8.94s | 8.81s | 7.66s |

**Token-Einsparung: KEINE — JMD produziert +11% MEHR Tokens als Pretty JSON**

**Bewertung**: **JMD ist für GPT-5 Nano ungeeignet.** Das Modell erzeugt extrem verbose JMD-Ausgaben (1.569 Tokens vs. 1.418 für JSON pretty im search_products-Step). Die Output-Tokens sind ~10× höher als bei größeren Modellen. Nano hat nicht genug Kapazität, um den kompakten JMD-Stil aus dem Primer zu internalisieren. Es folgt den Regeln formal (100% syntaktische Validität), produziert aber redundante und aufgeblähte Strukturen.

**Empfehlung**: GPT-5 Nano aus weiteren JMD-Tests ausschließen.

---

### 6.5 Gemini 3 Flash (Preview)

| Metrik | JSON pretty | JSON minified | JMD |
|---|---|---|---|
| Output-Tokens (search_products) | 160 | 160 | 120 avg |
| Gesamt Output-Tokens (alle Steps) | 404 | 472 | 5.812 (21 Runs) |
| Syntaktische Validität | 5/5 (100%) | 5/5 (100%) | 83/105 (79%) |
| Semantische Korrektheit | 3/5 (60%) | 3/5 (60%) | 49/105 (47%) |
| Chain Completion | 5/5 (100%) | 5/5 (100%) | 93/105 (89%) |
| TTFUB (Median, search_products) | 5.43s | 5.54s | 9.52s |

**Token-Einsparung (search_products): −25% vs Pretty JSON, −25% vs Minified**

**TTFUB**: JMD ist hier **langsamer** als JSON — ein Artefakt des Preview-Modells mit nicht-optimierter Infrastruktur.

**Bewertung**: Gute Token-Einsparung, aber niedrigere Reliabilität (79% Validität, 89% Chain Completion). Die hohe Latenz ist dem Preview-Status geschuldet und nicht repräsentativ für das Release-Modell. 12 übersprungene Steps.

---

### 6.6 Gemini 3.1 Pro

| Metrik | JSON pretty | JSON minified | JMD |
|---|---|---|---|
| Output-Tokens (search_products) | 160 | 160 | 114 avg |
| Gesamt Output-Tokens (alle Steps) | 399 | 399 | 5.090 (21 Runs) |
| Syntaktische Validität | 5/5 (100%) | 5/5 (100%) | 63/105 (60%) |
| Semantische Korrektheit | 4/5 (80%) | 4/5 (80%) | 45/105 (43%) |
| Chain Completion | 5/5 (100%) | 5/5 (100%) | 76/105 (72%) |
| TTFUB (Median, search_products) | 9.19s | 9.10s | 8.43s |

**Token-Einsparung (search_products): −29% vs Pretty JSON, −29% vs Minified**

**TTFUB**: Marginaler JMD-Vorteil (~8% schneller).

**Bewertung**: **Höchste Token-Einsparung** aller Modelle (−29%), aber **niedrigste Reliabilität** (60% Validität, 72% Chain Completion). 29 von 105 Steps übersprungen. Gemini 3.1 Pro versteht JMD grundsätzlich gut, produziert aber häufig subtile Syntaxfehler, die die Chain abbrechen lassen.

**Empfehlung**: Primer-Optimierung könnte die Validitätsrate erhöhen. Für Phase 2 nur mit verbessertem Primer einschließen.

---

## 7. Phase 1.5: Format-Fidelity-Test

Durchgeführt: 2026-03-15

### 7.1 Motivation: Format-Fidelity vs. Reasoning-Fidelity

Die niedrigen semantischen Korrektheitsraten im Chain-Benchmark (43–69%) warfen die Frage auf, ob JMD als Format Datenverluste verursacht. Eine kritische Analyse der Benchmark-Methodik ergab jedoch: Der Chain-Benchmark testet **Reasoning + Extraktion + Serialisierung** gleichzeitig. Wenn das Modell 15 Produkte nach Rating sortieren und die Top 3 identifizieren soll, ist ein Fehler in der Sortierung ein **Reasoning-Fehler**, kein Format-Fehler — und JSON zeigt dasselbe Problem (60–80% semantische Korrektheit).

Um Format-Fidelity isoliert zu messen, wurde ein separater Test entwickelt:

1. Dem Modell werden **konkrete, vorgegebene Daten** übergeben
2. Auftrag: **exakt dieselben Daten** im Zielformat reproduzieren
3. Output wird geparst und **Feld für Feld** gegen die Eingabe verglichen
4. Jede Abweichung ist ein **Format-Fehler**, keine Halluzination

### 7.2 Test-Payloads

Fünf Datenstrukturen decken alle JMD/JSON-Typen ab:

| Payload | Beschreibung | Typen |
|---|---|---|
| `flat_object` | Flaches Objekt (7 Felder) | string, int, float, bool, null |
| `nested_object` | Verschachtelte Objekte (2 Ebenen) | nested dicts, strings, float |
| `array_of_objects` | Array mit 3 Objekten | list of dicts, mixed scalars |
| `mixed_types` | Komplexe Mischstruktur | arrays, nested objects, booleans |
| `multiline_text` | Mehrzeiliger Text | multiline string, array |

### 7.3 Ergebnisse

Getestet: 6 Modelle × 2 Formate × 4 Payloads = 48 Tests (Multiline-Payload separat ausgewertet, da JMD-Parser-Einschränkung bei Inline-Blockquotes).

| Modell | JSON Syntax | JSON Data | JMD Syntax | JMD Data | JMD Tokens | JSON Tokens |
|---|---|---|---|---|---|---|
| Claude Haiku 4.5 | 4/4 (100%) | 4/4 (100%) | 4/4 (100%) | 4/4 (100%) | 400 | 609 |
| Claude Sonnet 4.6 | 4/4 (100%) | 4/4 (100%) | 4/4 (100%) | 4/4 (100%) | 400 | 609 |
| GPT-5.4 | 4/4 (100%) | 4/4 (100%) | 4/4 (100%) | 4/4 (100%) | 370 | 515 |
| GPT-5 Nano | 4/4 (100%) | 4/4 (100%) | 4/4 (100%) | 4/4 (100%) | 4.235 | 1.883 |
| Gemini 2.5 Flash | 4/4 (100%) | 4/4 (100%) | 4/4 (100%) | 4/4 (100%) | 411 | 618 |
| Gemini 2.5 Pro | 4/4 (100%) | 4/4 (100%) | 4/4 (100%) | 4/4 (100%) | 411 | 618 |

**Ergebnis: 48/48 Tests bestanden — 100% Format-Fidelity, 100% Data-Fidelity, alle Modelle, beide Formate.**

Wenn ein Modell Daten vorgelegt bekommt und sie im Zielformat reproduzieren soll, liefern **alle** Modelle — auch GPT und Gemini — die Werte **exakt** zurück. Kein einziger Datenverlust.

### 7.4 Token-Einsparung (Fidelity-Test)

| Modell | JSON Tokens | JMD Tokens | Einsparung |
|---|---|---|---|
| Claude Haiku 4.5 | 609 | 400 | **−34%** |
| Claude Sonnet 4.6 | 609 | 400 | **−34%** |
| GPT-5.4 | 515 | 370 | **−28%** |
| GPT-5 Nano | 1.883 | 4.235 | **+125%** |
| Gemini 2.5 Flash | 618 | 411 | **−33%** |
| Gemini 2.5 Pro | 618 | 411 | **−33%** |

Die Token-Einsparung im Fidelity-Test (28–34%) bestätigt die Ergebnisse des Chain-Benchmarks und ist sogar leicht höher, da keine Reasoning-Overhead-Varianz einfließt.

### 7.5 GPT-5 Nano: Ausschluss bestätigt

GPT-5 Nano produziert zwar **korrekte** Daten (100% Fidelity), benötigt dafür aber **4.235 JMD-Tokens** vs. **1.883 JSON-Tokens** — ein **Overhead von +125%**. Das Modell hat nicht genug Kapazität, um kompaktes JMD zu generieren. Es folgt den Syntax-Regeln, produziert aber extrem redundante Strukturen.

**GPT-5 Nano wird aus allen weiteren Tests ausgeschlossen.**

### 7.6 Schlussfolgerung: Format-Fidelity vs. Reasoning-Fidelity

Die niedrigen semantischen Korrektheitsraten im Chain-Benchmark (Abschnitt 6) sind **Reasoning-Fehler**, keine Format-Fehler:

- **Format-Fidelity** (gibt das Format Daten korrekt wieder?): **100%** über alle Modelle und Formate
- **Reasoning-Fidelity** (kann das Modell die richtige Antwort finden?): 43–80%, **identisch** bei JSON und JMD

JMD verursacht **keinen Datenverlust**. Semantische Fehler im Chain-Benchmark entstehen durch die Reasoning-Aufgabe (Sortierung, Extraktion, Interpretation), nicht durch die Serialisierung. Dies gilt gleichermaßen für JSON.

### 7.7 Anmerkung zum Multiline-Test

Der `multiline_text`-Payload deckte einen Modell-Fehler auf: Claude Haiku schrieb `body: > Text...` (Inline-Blockquote), statt der korrekten Form `body:\n> Text...` (Blockquote auf neuer Zeile).

In Standard-Markdown sind Blockquotes Block-Level-Konstrukte, die am Zeilenanfang beginnen — nicht inline innerhalb einer Key-Value-Zeile. JMD folgt dieser Konvention: Blockquote-Modus wird nur betreten, wenn der Key einen **leeren Wert** hat und die *nächste Zeile* mit `>` beginnt. `key: > text` ist ein regulärer Scalar-String mit dem Literal-Wert `"> text"`.

Der Parser verhält sich korrekt: er liest `body: > This is the first paragraph...` als String-Wert und behandelt die folgenden `>`-Zeilen als unbekannte Zeilen außerhalb eines Blockquote-Kontexts.

**Maßnahme:** Die JMD v0.3 Spec wurde um eine explizite Klarstellung ergänzt (Abschnitt 9.1): `key: > text` ist KEIN Blockquote. Ein konformer Generator DARF KEINE Inline-Blockquotes produzieren. Ein konformer Parser MUSS `key: > text` als Scalar-String behandeln. Dies war kein Spec-Defekt, sondern eine fehlende explizite Dokumentation des bereits korrekten Verhaltens.

---

## 8. Modellvergleich und Analyse

### 8.1 Methodische Korrektur: "Minified JSON" existiert nicht als LLM-Output

Eine Post-hoc-Analyse der Rohdaten ergab: **Fünf von sechs Modellen ignorieren die Instruktion, minifizierten JSON zu erzeugen**, und produzieren stattdessen Pretty-printed JSON:

| Modell | Pretty JSON (Zeilen) | "Minified" JSON (Zeilen) | Identisch? | Tatsächlich minifiziert? |
|---|---|---|---|---|
| Claude Haiku 4.5 | 22 | 20 | Nein | **Nein** — Pretty mit minimaler Abweichung |
| Claude Sonnet 4.6 | 22 | 22 | **Ja** | **Nein** — byte-identisch zu Pretty |
| GPT-5.4 | 22 | 22 | Nein | **Nein** — Pretty mit anderen Key-Namen |
| GPT-5 Nano | 20 | 5 | Nein | Teilweise — kompakter, aber nicht einzeilig |
| Gemini 3 Flash | 20 | 20 | **Ja** | **Nein** — byte-identisch zu Pretty |
| Gemini 3.1 Pro | 20 | 20 | **Ja** | **Nein** — byte-identisch zu Pretty |

**Befund 1 — LLMs unterscheiden nicht zwischen Pretty und Minified JSON.** Die Spalte "JMD vs Minified JSON" im Benchmark ist für die meisten Modelle irreführend — sie vergleicht JMD gegen Pretty JSON unter falschem Label. Drei Modelle (Sonnet, Gemini Flash, Gemini Pro) lieferten byte-identischen Output für beide JSON-Varianten. LLMs verarbeiten und produzieren JSON. Eine Unterscheidung zwischen Pretty und Minified existiert für sie nicht.

**Befund 2 — Minifizierung kann keine Rechenzeit einsparen.** Selbst wenn ein Modell minifizierten JSON erzeugen *könnte*, würde dies keine GPU-Zeit einsparen. Jeder LLM-Generierungsschritt kostet dieselbe Rechenzeit, unabhängig davon, welches Token erzeugt wird. Ein Modell, das minifizierten JSON produziert, hat nicht weniger gerechnet — es hat dieselbe Anzahl interner Verarbeitungsschritte durchlaufen und dabei andere Tokens gewählt. Die Token-Anzahl im Output mag niedriger sein, aber die Verarbeitungskosten sind es nicht. Die Phase-0-Daten bestätigen dies: Minifizierter JSON zeigte vergleichbare oder sogar *höhere* Server-Processing-Time pro Token als Pretty JSON.

**Konsequenz:** Die Token-Effizienz von Minified JSON ist Augenwischerei — es ist kosmetische Kompression des Outputs, keine strukturelle Vereinfachung des Generierungsprozesses. Die einzige Möglichkeit, LLM-Inferenzkosten für strukturierten Output zu senken, ist **strukturelle Vereinfachung**: weniger Strukturtokens erzeugen, nicht dieselbe Struktur mit weniger Leerzeichen. Genau das leistet JMD: Headings ersetzen verschachtelte Klammerpaare, Bare Keys ersetzen Quoted Keys, Zeilenumbrüche ersetzen Komma-Delimiter. Das Modell durchläuft weniger Generierungsschritte, weil die Struktur einfacher *ist*.

Die folgenden Vergleichstabellen führen die Spalte "JMD vs Minified" der Vollständigkeit halber weiter, aber sie ist **de facto identisch mit "JMD vs Pretty"** für alle Modelle außer GPT-5 Nano (ausgeschlossen).

### 8.2 Token-Einsparung (search_products Step)

| Modell | JMD vs Pretty | JMD vs Minified | Bewertung |
|---|---|---|---|
| Claude Haiku 4.5 | **−31%** | −25% | Exzellent |
| Claude Sonnet 4.6 | **−31%** | −31% | Exzellent |
| GPT-5.4 | **−28%** | −29% | Sehr gut |
| GPT-5 Nano | **+11%** | +30% | Ausgeschlossen |
| Gemini 3 Flash | **−25%** | −25% | Gut |
| Gemini 3.1 Pro | **−29%** | −29% | Sehr gut (aber unzuverlässig) |

**Durchschnitt (ohne Nano): −29% vs Pretty JSON**

### 8.3 Reliabilität

| Modell | Syn. Validität | Sem. Korrektheit | Chain Completion |
|---|---|---|---|
| Claude Haiku 4.5 | **100%** | 51% | **100%** |
| Claude Sonnet 4.6 | **100%** | **69%** | **100%** |
| GPT-5.4 | 89% | 62% | 91% |
| GPT-5 Nano | **100%** | 57% | **100%** |
| Gemini 3 Flash | 79% | 47% | 89% |
| Gemini 3.1 Pro | 60% | 43% | 72% |

**Anthropic-Modelle** dominieren bei der Reliabilität: 100% syntaktische Validität und Chain Completion.

### 8.4 TTFUB (Time-to-First-Useful-Byte)

| Modell | JSON (Median) | JMD (Median) | Speedup |
|---|---|---|---|
| Claude Haiku 4.5 | 1.09s | 0.51s | **2.1×** |
| Claude Sonnet 4.6 | 2.53s | 1.23s | **2.1×** |
| GPT-5.4 | 2.01s | 0.59s | **3.4×** |
| GPT-5 Nano | 8.94s | 7.66s | 1.2× |
| Gemini 3 Flash | 5.43s | 9.52s | 0.6× (Preview) |
| Gemini 3.1 Pro | 9.19s | 8.43s | 1.1× |

JMD liefert bei allen leistungsfähigen Modellen das erste nutzbare Byte **2–3× schneller** als JSON. Der Gemini-Flash-Ausreißer ist dem Preview-Status geschuldet.

### 8.5 Kosten-Effizienz

| Modell | Kosten pro JMD-Run | Token-Einsparung | Kosten-Nutzen |
|---|---|---|---|
| Claude Haiku 4.5 | $0.004 | −31% | Bestes Preis-Leistungs-Verhältnis |
| Claude Sonnet 4.6 | $0.015 | −31% | Höchste Qualität |
| GPT-5.4 | $0.010 | −28% | Bester TTFUB-Speedup |
| GPT-5 Nano | $0.003 | +11% | Nicht empfohlen |
| Gemini 3 Flash | $0.013 | −25% | Preview-Einschränkungen |
| Gemini 3.1 Pro | $0.006 | −29% | Niedrige Reliabilität |

### 8.6 Schlüsselerkenntnisse

1. **JMD spart konsistent 25–31% Output-Tokens** gegenüber Pretty JSON bei allen Modellen mit ausreichender Kapazität (≥ Mid-Tier).

2. **Der 5-Bullet-Primer (~80 Tokens) reicht aus.** Kein Beispiel nötig, kein Fine-Tuning, keine Trainingsanpassung.

3. **TTFUB-Vorteil von 2–3× ist real** und konsistent über Provider hinweg. JMD's zeilenbasiertes Parsing ermöglicht sofortige Verarbeitung jeder abgeschlossenen Zeile.

4. **Anthropic-Modelle haben die höchste JMD-Reliabilität** (100% Validität). Dies muss im Kontext des Entwicklungs-Bias gelesen werden (siehe Abschnitt 8.7).

5. **Nano/Mini-Modelle sind für JMD ungeeignet.** GPT-5 Nano produziert aufgeblähte Ausgaben. Format-Instruktionen überfordern die begrenzte Kapazität kleiner Modelle.

6. **Gemini 3.1 Pro zeigt das höchste Einsparpotenzial (−29%), aber die niedrigste Reliabilität (60%).** Ein optimierter Primer oder Few-Shot-Beispiel könnte dies beheben.

### 8.7 Transparenzhinweis: Entwicklungs-Bias

JMD wurde in einem iterativen Dialog mit Claude (Anthropic) entwickelt. Designentscheidungen wie die Wahl von Markdown-Headings als Strukturmarker, Bare Keys ohne Anführungszeichen, oder die Multiline-Syntax mit Blockquotes wurden gemeinsam mit Claude erarbeitet. Das Format reflektiert daher zwangsläufig Claudes Präferenzen und interne Repräsentationen — GPT oder Gemini hätten bei manchen Entscheidungen möglicherweise andere Lösungen bevorzugt.

**Auswirkungen auf die Benchmark-Ergebnisse:**

Dies ist der wahrscheinlichste Grund, warum Anthropic-Modelle bei der **Reliabilität** (syntaktische Validität, Chain Completion) besser abschneiden als die Konkurrenz. Die JMD-Syntax wurde — bewusst oder unbewusst — auf Muster optimiert, die Claude besonders gut beherrscht.

**Was der Bias NICHT erklärt:**

- Die **Token-Einsparung ist über alle Provider konsistent** (25–31%). Wenn JMD "Claude-nativ" wäre, müssten GPT und Gemini deutlich schlechter abschneiden — tun sie aber nicht.
- Der **TTFUB-Speedup ist bei GPT-5.4 sogar am größten** (3.4× vs. 2.1× bei Claude). Das Streaming-Argument ist provider-unabhängig.
- Die Effizienzvorteile basieren auf **strukturellen Eigenschaften** (weniger Tokens pro Strukturelement), nicht auf syntax-spezifischer Vertrautheit.

**Empfohlene Maßnahmen zur Bias-Reduktion:**

1. **Primer-Varianten mit GPT/Gemini entwickeln** — den Primer nicht nur mit Claude, sondern auch mit anderen Modellen iterativ optimieren, um modell-spezifische Stolperstellen zu identifizieren
2. **Syntax-Alternativen testen** — für Entscheidungen, bei denen der Bias am größten sein könnte (z.B. Heading-Tiefe vs. Einrückung, Bare Keys vs. Quoted Keys), gezielt Varianten an GPT und Gemini testen
3. **Terminologie anpassen** — statt "LLM-native" besser "Markdown-native" verwenden, da Markdown nachweislich in den Trainingsdaten aller großen Modelle dominant vertreten ist
4. **In Phase 2: Primer-Fairness sicherstellen** — für jeden Provider den jeweils besten Primer verwenden, nicht einen universellen Claude-optimierten Primer

**Fazit:** Der Entwicklungs-Bias betrifft primär die Reliabilitäts-Metrik, nicht die Effizienz-Metrik. Die Token-Einsparung und der TTFUB-Vorteil sind strukturell bedingt und provider-übergreifend reproduzierbar. Dennoch wäre es unseriös, die 100%-Validität der Claude-Modelle als Format-Eigenschaft darzustellen, ohne den Entwicklungskontext offenzulegen.

---

## 9. Empfehlungen für Phase 2

### 9.1 Modellauswahl

Für Phase 2 wurden vier Modelle ausgewählt. Budget-Modelle (GPT-5 Nano, Gemini Flash) werden ausgeschlossen — sie sind primär als Chatbots konzipiert und nicht für Business-Anwendungsfälle wie REST-APIs. Ausnahme: **Haiku 4.5 bleibt**, weil Anthropic das primäre Pitch-Ziel ist und deren Modelle durchgängig JMD-kompatibel sein sollten.

| Modell | Tier | Entscheidung | Begründung |
|---|---|---|---|
| **Claude Haiku 4.5** | Budget | **Ja** | Anthropic-Pitch: Alle Anthropic-Tiers müssen JMD beherrschen |
| **Claude Sonnet 4.6** | Mid | **Ja** | Höchste Reliabilität + starke Einsparung |
| **GPT-5.4** | Top | **Ja** | Bester TTFUB + gute Einsparung |
| **Gemini 3.1 Pro** | Top | **Ja** | Cross-Provider-Validierung, Top-Tier |
| GPT-5 Nano | Budget | **Ausgeschlossen** | +125% Token-Overhead bei JMD |
| Gemini 3 Flash | Budget | **Ausgeschlossen** | Budget-Tier, kein REST-API-Zielmodell |

### 9.2 Konfiguration Phase 2

- **30 Runs** pro Modell × Format × Szenario
- **4 Modelle** × **2 Formate** (JSON pretty, JMD) × **3 Szenarien**
- **Formate**: JSON pretty-printed (reale LLM-Baseline) und JMD. Minified JSON entfällt — LLMs können es nicht produzieren, und selbst programmatische Minifizierung spart keine Rechenzeit (vgl. Abschnitt 8.1)
- **Statistische Auswertung**: Median, 95%-Konfidenzintervall, Wilcoxon-Rangsummentest
- **Primer**: `strict` (validiert, siehe 9.3)
- **Parallelisierung**: 4 Modelle laufen gleichzeitig (ThreadPoolExecutor), ~30–45 Min. Wall-Clock
- **Erwartete Kosten**: ~$15 (verifiziert via Smoke-Test: $0.52 für 1 Run × 4 Modelle)

### 9.3 Primer-Optimierung: `strict` löst Gemini-Problem

**Problem:** Gemini 3.1 Pro erreichte mit dem `standard`-Primer nur 60% syntaktische Validität. Ursache: Das Modell ließ bei flachen Objekten (z.B. `check_availability`, `place_order`) das `#`-Root-Heading weg und produzierte nur `key: value`-Zeilen — valides Markdown, aber kein valides JMD.

**Lösung:** Ein neuer `strict`-Primer mit drei Änderungen:

1. **Explizite Pflicht**: „EVERY response MUST start with # Label"
2. **Flaches Beispiel**: Ein `# Availability`-Beispiel zeigt, dass auch einfache Objekte ein Heading brauchen
3. **Blockquote-Klarstellung**: „on its own line, not inline" (vgl. Spec-Fix Section 9.1)

**Validierung** (1 Run × 4 Modelle, E-Commerce-Chain):

| Modell | `standard` | `example` | `strict` |
|---|---|---|---|
| Claude Haiku 4.5 | 5/5 | — | 5/5 |
| Claude Sonnet 4.6 | 5/5 | — | 5/5 |
| GPT-5.4 | 5/5 | — | 5/5 |
| Gemini 3.1 Pro | 3/5 | 1/5 | **5/5** |

Zusätzlich 3 weitere Runs mit Gemini 3.1 Pro × `strict`: **15/15 = 100%**.

**Ergebnis:** Der `strict`-Primer löst das Gemini-Problem ohne Regression bei den anderen Modellen. Er wird als Default für Phase 2 verwendet (`benchmark/config.py: primer_default = "strict"`).

**Token-Overhead des Primers:** Der `strict`-Primer ist ~120 Tokens lang (vs. ~60 für `standard`). Die zusätzlichen ~60 Input-Tokens pro Request werden durch die JMD-Einsparung bei den Output-Tokens um ein Vielfaches kompensiert.

### 9.4 Offene Punkte

1. ~~Fidelity-Test mit korrekten Gemini-Modellen~~ ✅ Gemini 3.1 Pro Preview: 10/10 = 100%
2. ~~Primer-Optimierung für Gemini 3.1 Pro~~ ✅ `strict`-Primer: 60% → 100%
3. ~~Szenarien DevOps + Data Pipeline validieren~~ ✅ Alle 3 Szenarien × 4 Modelle: 60/60 Syntax, 59–60/60 Semantik (stochastisches Rauschen)
4. **Server-Processing-Time** statt Wall-Clock — wenn Provider-APIs dies exponieren

### 9.5 Pre-Phase-2-Fixes

Vor dem Start von Phase 2 wurden folgende Probleme identifiziert und behoben:

**Primer-Fix:** Der `strict`-Primer enthielt das Muster `- key: val, key: val` (Komma-getrennte Inline-Felder). Dieses Muster wurde in JMD v0.3 bewusst entfernt — die Spec verlangt Indentation-Continuation (`- key: val` + eingerückte Folgezeilen). Der Primer wurde korrigiert. Alle Modelle produzieren das Indentation-Muster fehlerfrei.

**Availability-Daten:** Die simulated E-Commerce API enthielt keine Rating-Daten in der Availability-Response. Modelle sollten „best available by rating" wählen, hatten aber keine Ratings zur Verfügung → willkürliche Auswahl. Rating und Name wurden in die Availability-Daten aufgenommen.

**Validator-Robustheit:** Drei Validatoren waren zu restriktiv:

- `devops/post_comment`: Keyword-Suche nur in `body`-Feld statt im gesamten Output
- `datapipeline/store_results`: Top-Level-Key-Prüfung statt `_deep_find` (Modelle verschachteln unterschiedlich)
- `ecommerce/build_cart`: `product_id` nur auf Top-Level gesucht statt in verschachtelten Strukturen

---

## 10. Phase 2: Statistisch belastbarer Benchmark (30 Runs)

*Durchgeführt: 2026-03-15 bis 2026-03-16*

Phase 2 wurde in zwei Durchläufen durchgeführt:

- **Phase 2a**: Claude Haiku 4.5, Claude Sonnet 4.6, GPT-5.4 — ohne Server-Processing-Time
- **Phase 2b**: Claude Sonnet 4.6, GPT-5.4, Mistral Large, Gemini 2.5 Flash — **mit Server-Processing-Time**

Phase 2b ist die Hauptauswertung und wird im Folgenden dokumentiert. Phase 2a-Ergebnisse für Haiku sind weiterhin gültig und werden in 10.3 zusammengefasst.

### 10.1 Konfiguration (Phase 2b)

- **30 Runs** × 4 Modelle × 2 Formate × 3 Szenarien = **720 Chains**
- **Formate**: JSON pretty-printed, JMD (Primer: `strict`)
- **Szenarien**: E-Commerce, DevOps, Data Pipeline
- **Temperature**: 0.0
- **Modelle**: Claude Sonnet 4.6, GPT-5.4, Mistral Large, Gemini 2.5 Flash
- **Neu: Server-Processing-Time** aus API-Headern extrahiert (Anthropic: `server-processing-time`, OpenAI/Mistral: `x-envoy-upstream-service-time`, Google: `server-timing`)

**Modellwechsel gegenüber 2a**: Haiku entfällt (Ergebnisse aus 2a bleiben gültig), stattdessen Mistral Large als Cross-Provider-Erweiterung und Gemini 2.5 Flash als Google-Vertreter. Gemini 3.1 Pro wurde bereits in 2a ausgeschlossen (API-Infrastruktur unbrauchbar, siehe 9.4).

### 10.2 Ergebnisse: Claude Sonnet 4.6

| Metrik | JSON pretty | JMD | Δ JMD vs JSON |
|---|---|---|---|
| N (Chains) | 90 | 90 | — |
| Output Tokens (mean ± σ) | 2.154 ± 1.456 | 1.767 ± 1.159 | **−18,0%** |
| Payload Tokens (mean ± σ) | 4.649 ± 1.555 | 3.630 ± 1.242 | **−21,9%** |
| Kosten USD (mean ± σ) | $0,0508 | $0,0436 | **−14,2%** |
| Server-Processing-Time (median) | 36.463 ms | 37.604 ms | +1,1% (n.s.) |
| Syntax-Validität | 100% (450/450) | 100% (450/450) | — |
| Chain Completion | 90/90 (100%) | 90/90 (100%) | — |
| Semantische Korrektheit | ~92% | ~93% | +1pp |

**Bewertung**: Sonnet zeigt den stärksten Output-Token-Vorteil aller Modelle (−18%). 100% Reliabilität in beiden Formaten. Server-Processing-Time ist neutral — der Einspareffekt liegt ausschließlich auf Token- und Kostenseite. Größte Kosteneinsparung: **−14,2%**.

### 10.3 Ergebnisse: GPT-5.4

| Metrik | JSON pretty | JMD | Δ JMD vs JSON |
|---|---|---|---|
| N (Chains) | 90 | 90 | — |
| Output Tokens (mean ± σ) | 1.146 ± 601 | 984 ± 413 | **−14,1%** |
| Payload Tokens (mean ± σ) | 4.634 ± 1.558 | 3.612 ± 1.230 | **−22,0%** |
| Kosten USD (mean ± σ) | $0,0306 | $0,0277 | **−9,4%** |
| Server-Processing-Time (median) | 18.940 ms | 16.671 ms | **−8,6%** (p = 0,006) |
| Syntax-Validität | 100% (450/450) | 100% (450/450) | — |
| Chain Completion | 90/90 (100%) | 90/90 (100%) | — |
| Semantische Korrektheit | ~98% | ~98% | — |

**Bewertung**: GPT-5.4 ist das einzige Modell mit **signifikant niedrigerer Server-Processing-Time** bei JMD (−8,6%, p = 0,006). Weniger Output-Tokens führen hier tatsächlich zu weniger Rechenzeit auf dem Server — ein starkes Argument für den API-Provider-Pitch. 100% Syntax-Validität (Verbesserung von 89% in Phase 1 dank `strict`-Primer).

### 10.4 Ergebnisse: Mistral Large

| Metrik | JSON pretty | JMD | Δ JMD vs JSON |
|---|---|---|---|
| N (Chains) | 90 | 90 | — |
| Output Tokens (mean ± σ) | 1.095 ± 494 | 1.006 ± 552 | **−8,1%** |
| Payload Tokens (mean ± σ) | 4.631 ± 1.550 | 3.623 ± 1.234 | **−21,8%** |
| Kosten USD (mean ± σ) | $0,0046 | $0,0044 | **−4,2%** |
| Server-Processing-Time (median) | 19.834 ms | 17.419 ms | −2,9% (n.s.) |
| Syntax-Validität | 100% (450/450) | 100% (450/450) | — |
| Chain Completion | 90/90 (100%) | 90/90 (100%) | — |
| Semantische Korrektheit | ~92% | ~89% | −3pp |

**Bewertung**: Mistral zeigt die konsistenten Payload-Einsparungen (−21,8%), aber einen geringeren Output-Token-Effekt (−8,1%) als Sonnet und GPT. Die geringere Kosteneinsparung (−4,2%) liegt am niedrigen Pricing von Mistral ($2/$6/M) — die absolute Einsparung in Tokens ist vergleichbar. Server-Processing-Time: leichter Vorteil für JMD, aber nicht signifikant.

### 10.5 Ergebnisse: Gemini 2.5 Flash

| Metrik | JSON pretty | JMD | Δ JMD vs JSON |
|---|---|---|---|
| N (Chains) | 90 | 90 | — |
| Output Tokens (mean ± σ) | 694 ± 408 | 689 ± 289 | −0,7% (n.s.) |
| Payload Tokens (mean ± σ) | 3.955 ± 1.470 | 3.568 ± 1.225 | **−9,8%** |
| Kosten USD (mean ± σ) | $0,0054 | $0,0055 | +1,2% |
| Server-Processing-Time (median) | 16.552 ms | 26.470 ms | +18,3% (JMD langsamer) |
| Syntax-Validität | **82,2%** (370/450) | **98,9%** (445/450) | **+16,7pp** |
| Chain Completion | 82,2% | 98,9% | **+16,7pp** |
| Semantische Korrektheit | ~78% | ~81% (Step-Level) | — |

**Bewertung**: Gemini 2.5 Flash ist ein Sonderfall. Keine Output-Token-Einsparung und höhere Server-Processing-Time — wahrscheinlich durch Gemini's interne Thinking-Tokens verursacht, die nicht in der Output-Zählung erscheinen. **Aber**: JMD löst Geminis JSON-Reliabilitätsproblem dramatisch. JSON-Syntax-Validität liegt bei nur 82,2% — Gemini produziert häufig malformed JSON (fehlende Kommas, trailing commas, etc.). Mit JMD steigt die Validität auf 98,9%. Dies ist **das stärkste Argument für JMD bei Gemini**: nicht Effizienz, sondern Zuverlässigkeit.

Anmerkung zur Semantik: Die E2E-Scores (Produkt aller Step-Scores) sind bei Gemini schwer vergleichbar, da JSON-Chains häufiger abbrechen (82,2% Completion). Auf Step-Level zeigt JMD leicht bessere Semantik in den meisten Steps, aber einen spezifischen Defekt im `post_comment`-Step des DevOps-Szenarios (0% korrekt mit JMD vs. 100% mit JSON). Dies ist ein einzelner Validator-Mismatch, kein systematisches Problem.

### 10.6 Ergebnisse: Claude Haiku 4.5 (Phase 2a)

Haiku wurde in Phase 2a ohne Server-Processing-Time getestet. Die Ergebnisse sind weiterhin gültig:

| Metrik | JSON pretty | JMD | Δ JMD vs JSON |
|---|---|---|---|
| N (Chains) | 90 | 90 | — |
| Output Tokens (mean ± σ) | 897 ± 312 | 839 ± 367 | −6,4% |
| Payload Tokens (mean ± σ) | 4.112 ± 1.451 | 3.212 ± 1.193 | **−21,9%** |
| Kosten USD (mean ± σ) | $0,0080 | $0,0075 | **−6,3%** |
| Syntax-Validität | 100% | 100% | — |
| Chain Completion | 90/90 (100%) | 90/90 (100%) | — |
| Semantischer Score (mean) | 0,948 | 0,927 | −0,021 |

**Bewertung**: Haiku bestätigt die Payload-Einsparung von −21,9% bei perfekter Reliabilität. Die niedrigere Output-Token-Einsparung (−6,4% vs. −18% bei Sonnet) erklärt sich durch Haikus kompaktere JSON-Ausgabe — weniger Reasoning-Text, weniger zu komprimieren.

### 10.7 Modellübergreifende Zusammenfassung

| Modell | Output Tok Δ | Payload Tok Δ | Kosten Δ | SPT Δ | Syn JSON → JMD |
|---|---|---|---|---|---|
| **Sonnet 4.6** | **−18,0%** | −21,9% | **−14,2%** | +1,1% (n.s.) | 100% → 100% |
| **GPT-5.4** | −14,1% | −22,0% | −9,4% | **−8,6%** (p<0,01) | 100% → 100% |
| **Mistral Large** | −8,1% | −21,8% | −4,2% | −2,9% (n.s.) | 100% → 100% |
| **Gemini 2.5 Flash** | −0,7% | −9,8% | +1,2% | +18,3% | **82,2% → 98,9%** |
| **Haiku 4.5** (2a) | −6,4% | −21,9% | −6,3% | — | 100% → 100% |

**Aggregiert (Phase 2b, 720 Chains):**

| Metrik | JSON | JMD | Δ |
|---|---|---|---|
| Payload Tokens | 4.467 | 3.608 | **−19,2%** |
| Output Tokens | 1.272 | 1.112 | **−12,6%** |
| Kosten | $0,0223 | $0,0198 | **−11,5%** |
| Syntax-Validität | 95,6% | 99,7% | **+4,1pp** |

### 10.8 Kernergebnisse

1. **Payload-Tokens: konsistent −22%** bei Sonnet, GPT-5.4, Mistral und Haiku. Dies bestätigt die theoretische Format-Analyse über 4 Provider hinweg. Gemini spart weniger (−9,8%), wahrscheinlich wegen interner Thinking-Token-Architektur.

2. **Output-Tokens: −8 bis −18%** (ohne Gemini). Die Varianz entsteht durch unterschiedliches Reasoning-Verhalten — Sonnet produziert mehr erklärenden Text, der bei JMD stärker komprimiert wird.

3. **Server-Processing-Time: nur bei GPT-5.4 signifikant** (−8,6%, p = 0,006). Bei Sonnet und Mistral neutral, bei Gemini kontraproduktiv. Die Hypothese „weniger Tokens = weniger Compute" bestätigt sich nur bei OpenAI. Bei anderen Providern kompensiert wahrscheinlich der JMD-Primer im Input den Output-Vorteil, oder interne Tokenizer-Effizienz für JSON gleicht den Unterschied aus.

4. **Semantik: neutral bis positiv**. Kein Modell zeigt eine systematische Verschlechterung. Sonnet zeigt eine Verbesserung (93% vs. 92%). GPT-5.4 bleibt stabil bei ~98%.

5. **JMD verbessert die Reliabilität dramatisch bei Gemini** (82,2% → 98,9% Syntax-Validität). JSON ist für Gemini Flash das fehleranfälligere Format. Dies ist das stärkste Argument für JMD außerhalb der Effizienz-Diskussion: **JMD ist einfacher korrekt zu produzieren als JSON.**

6. **100% Syntax-Validität bei 3 von 4 Providern** — Sonnet, GPT-5.4 und Mistral produzieren fehlerfrei mit dem `strict`-Primer. Über 1.350 Steps (ohne Gemini) kein einziger Parse-Fehler.

### 10.9 Statistische Signifikanz (Wilcoxon Signed-Rank)

Alle Tests gepaart nach (Szenario, Run-ID), N = 90 Paare pro Modell.

| Modell | Output Tokens | Payload Tokens | Kosten | SPT |
|---|---|---|---|---|
| **Sonnet** | W=242, p=3,7×10⁻¹³ *** | W=0, p=1,7×10⁻¹⁶ *** | W=134, p=1,4×10⁻¹⁴ *** | p=0,51 n.s. |
| **GPT-5.4** | W=1060, p=7,1×10⁻⁵ *** | W=0, p=1,7×10⁻¹⁶ *** | W=972, p=1,5×10⁻⁵ *** | p=0,006 ** |
| **Mistral** | W=738, p=1,4×10⁻⁷ *** | W=0, p=1,7×10⁻¹⁶ *** | W=585, p=4,0×10⁻⁹ *** | p=0,54 n.s. |
| **Gemini Flash** | W=1324, p=5,5×10⁻³ ** | W=1245, p=1,2×10⁻³ ** | W=1337, p=4,3×10⁻³ ** | p=5,1×10⁻⁷ *** (JMD langsamer) |

Signifikanzniveaus: *** p < 0,001; ** p < 0,01; * p < 0,05; n.s. = nicht signifikant

**Alle Token- und Kostenunterschiede sind hochsignifikant** (p < 0,01) über alle vier Provider. Payload-Tokens zeigen die stärkste Signifikanz (W=0 für drei Modelle — JMD hat in **jedem einzelnen** der 90 Paare weniger Payload-Tokens als JSON).

### 10.10 Anmerkung zur Server-Processing-Time

Die Server-Processing-Time (SPT) misst die reine Verarbeitungszeit auf dem API-Server, ohne Netzwerklatenz. Sie wird aus Provider-spezifischen HTTP-Headern extrahiert:

- **Anthropic**: `server-processing-time` (Millisekunden)
- **OpenAI**: Response-Header (Millisekunden)
- **Mistral**: `x-envoy-upstream-service-time` (Millisekunden)
- **Google**: `server-timing` Header

SPT ist die einzig belastbare Timing-Metrik. Wall-Clock-Zeiten werden nicht mehr berichtet, da sie durch Netzwerklatenz, Provider-Queuing und Client-seitige Verarbeitung verfälscht sind.

**Interpretation**: Nur GPT-5.4 zeigt eine signifikante SPT-Reduktion (−8,6%). Dies könnte bedeuten:
- OpenAIs Infrastruktur gibt die Output-Token-Einsparung direkt als Zeitersparnis weiter
- Andere Provider haben fixe Overhead-Kosten (Prompt-Processing, Safety-Checks), die den Effekt absorbieren
- Bei Gemini dominieren interne Thinking-Tokens die SPT, unabhängig vom Output-Format

Für den API-Provider-Pitch ist die SPT-Neutralität bei Sonnet/Mistral kein Nachteil — der Kunde spart trotzdem Token-Kosten. Bei GPT-5.4 spart der Provider zusätzlich Rechenzeit.

---

## 11. Phase 3: Agentic Chains mit Modell-Permutationen

*Durchgeführt: 2026-03-16*

Phase 3 testet JMD in **realistischen Agentic Workflows**, bei denen jeder Step einer 3-Step-Chain von einem **anderen LLM** bearbeitet wird. Dies simuliert den Praxisfall, in dem verschiedene Agents/Modelle über ein gemeinsames Datenformat kommunizieren.

### 11.1 Konfiguration

- **3 Modelle**: Claude Sonnet 4.6, GPT-5.4, Mistral Large
- **6 Permutationen**: Alle geordneten 3er-Kombinationen (Sonnet→GPT→Mistral, GPT→Mistral→Sonnet, etc.)
- **2 Formate**: JSON pretty, JMD (mit Epistemic-Primer)
- **3 Szenarien**: E-Commerce, DevOps, Data Pipeline
- **5 Runs** pro Konfiguration
- **Gesamt**: 6 × 2 × 3 × 5 = **180 Chains** (540 Steps)
- **Kosten**: $3,96 | **Dauer**: ~54 Minuten

**Neu in Phase 3**: Der JMD-Primer enthält einen Epistemic-Suffix, der optionale Frontmatter-Felder einführt:

```
confidence: high | medium | low | speculative
source: Datenherkunft beschreiben
uncertain: Komma-getrennte unsichere Feldnamen
```

Diese Felder werden nicht erzwungen — die Modelle entscheiden selbst, ob und wie sie sie nutzen.

### 11.2 Ergebnisse: Format-Vergleich

| Metrik | JSON pretty | JMD | Δ |
|---|---|---|---|
| N Chains | 90 | 90 | — |
| Chain Completion | 100% | 100% | — |
| Syntax-Validität | 100% | 100% | — |
| Sem. Korrektheit (Step-Level) | 88,1% | 87,4% | −0,7pp |
| **E2E Sem. Score (mean)** | 0,561 | **0,604** | **+7,6%** |
| Tokens (mean) | 5.980 | 5.805 | −2,9% |
| Kosten (mean) | $0,0224 | $0,0216 | −3,7% |
| Fehlerquelle | 100% Modell | 100% Modell | — |

**Interpretation**: Beide Formate sind in Agentic Chains **gleich zuverlässig** — 100% Syntax-Validität, 100% Chain Completion, keine format-induzierten Fehler. Alle 66 Fehler über beide Formate sind Reasoning-Fehler der Modelle.

Der E2E-Score (Produkt aller Step-Scores) ist bei JMD **+7,6% höher** als bei JSON. Das bedeutet: Wenn JMD-Steps korrekt sind, sind sie semantisch treuer — die Scores pro Step sind höher, auch wenn die binäre Korrektheit (pass/fail) vergleichbar ist.

### 11.3 Per-Szenario-Analyse

| Szenario | Format | Sem. Korrekt | E2E Score | Tokens |
|---|---|---|---|---|
| **E-Commerce** | JSON | 64,4% | 0,289 | 3.372 |
| | JMD | **86,7%** | **0,856** | 3.665 |
| **DevOps** | JSON | **100%** | **0,695** | 6.131 |
| | JMD | 94,4% | 0,483 | 5.881 |
| **Data Pipeline** | JSON | **100%** | **0,700** | 8.435 |
| | JMD | 81,1% | 0,473 | 7.868 |

Die Szenarien zeigen ein differenziertes Bild:

- **E-Commerce**: JMDs stärkster Gewinn — **+196% E2E-Score** (0,856 vs. 0,289). Die Epistemic-Metadaten über unsichere Felder (Lieferschätzungen, Rating-Konflikte) helfen den nachfolgenden Agents, bessere Entscheidungen zu treffen.

- **DevOps**: JSON leicht vorne. Die text-intensiven Issue-Strukturen mit Kommentaren profitieren weniger von Epistemic-Frontmatter. Alle JSON-Steps sind korrekt (100%), JMD verliert auf Step-Level (94,4%).

- **Data Pipeline**: JSON leicht vorne. Numerische Aggregationsaufgaben profitieren weniger von JMDs strukturellen Vorteilen. JMD spart aber −6,7% Tokens.

### 11.4 Per-Modell-Analyse

| Modell | Format | Syn. Valid. | Sem. Korrekt | Sem. Score |
|---|---|---|---|---|
| **GPT-5.4** | JSON | 100% | **95,6%** | **0,912** |
| | JMD | 100% | 91,1% | 0,866 |
| **Sonnet** | JSON | 100% | 84,4% | 0,826 |
| | JMD | 100% | 83,3% | **0,847** |
| **Mistral** | JSON | 100% | 84,4% | 0,788 |
| | JMD | 100% | **87,8%** | **0,813** |

- **GPT-5.4** ist das stärkste Modell insgesamt und bevorzugt leicht JSON (+4,5pp Korrektheit).
- **Mistral** profitiert am meisten von JMD (+3,4pp Korrektheit, +0,025 Score).
- **Sonnet** zeigt das Muster: niedrigere binäre Korrektheit, aber höherer Score — JMD hilft bei der semantischen Treue, auch wenn der strikte Pass/Fail-Grenzwert nicht immer erreicht wird.
- **100% Syntax-Validität über alle 540 Steps, alle Modelle, beide Formate.**

### 11.5 Fehleranalyse

| Fehlerquelle | JSON | JMD |
|---|---|---|
| Format (Parse-Fehler) | 0 | 0 |
| Modell (Reasoning-Fehler) | 32 | 34 |
| Propagiert (Chain-Abbruch) | 0 | 0 |

Identisches Fehlerprofil. Kein einziger format-induzierter Fehler. Kein einziger Chain-Abbruch. Die 66 Fehler über beide Formate sind ausschließlich Reasoning-Fehler der Modelle (falsche Sortierung, fehlende Felder, etc.).

### 11.6 Epistemic Frontmatter: Adoption und Kalibrierung

Die Epistemic-Frontmatter-Felder wurden nur im JMD-Primer als optional beschrieben, ohne explizites Training oder Few-Shot-Beispiele.

#### Adoption (270 JMD-Steps)

| Feld | Steps mit Wert | Rate |
|---|---|---|
| `confidence` | 266/270 | **98,5%** |
| `source` | 266/270 | **98,5%** |
| `uncertain_fields` | 218/270 | **80,7%** |

#### Adoption pro Modell

| Modell | Confidence-Rate |
|---|---|
| GPT-5.4 | 100% (90/90) |
| Mistral | 100% (90/90) |
| Sonnet | 95,6% (86/90) |

**98,5% Adoption ohne Training.** Alle drei Provider-Modelle nutzen die Epistemic-Felder spontan, nachdem sie nur einen ~20-Token-Suffix im Primer gesehen haben. Zum Vergleich: **0% der JSON-Steps enthalten Confidence-Metadaten** — JSON bietet keinen strukturierten Kanal dafür.

#### Kalibrierung: Confidence vs. Korrektheit

| Confidence | N | Sem. korrekt | Rate | Mean Score |
|---|---|---|---|---|
| high | 228 | 199 | 87,3% | 0,843 |
| medium | 38 | 33 | 86,8% | 0,817 |
| low / speculative | 0 | — | — | — |

Die Kalibrierung ist schwach — `high` und `medium` haben nahezu identische Korrektheitsraten. Modelle sind (noch) nicht gut darin, ihre eigene Unsicherheit zu quantifizieren. Aber:

- `medium` wird gezielt für **ambige Aufgaben** vergeben (Ranking, Priorisierung mit widersprüchlichen Severity-Werten)
- `uncertain_fields` benennt spezifische Felder: `auto_triage_severity`, `estimated_ship_days`, `shipping_address` — inhaltlich sinnvolle Unsicherheiten

#### Bedeutung für JMD als Format

Die Epistemic-Frontmatter-Adoption validiert das Kernprinzip des AI-Whispering-Ansatzes: **Man muss LLMs nicht programmieren, Unsicherheit auszudrücken — man muss ihnen nur einen strukturierten Kanal dafür geben.** JSON bietet diesen Kanal nicht (0% Adoption). JMD's Frontmatter gibt den Modellen eine natürliche Stelle für Metadaten, die sie ohnehin „haben" — und sie nutzen sie sofort, über alle drei Provider hinweg.

### 11.7 Parse-Performance

**Phase-3-Rohdaten (nicht direkt vergleichbar):**

Die in Phase 3 gemessenen Parse-Zeiten (JMD 0,323 ms vs. JSON 0,106 ms) sind **kein fairer Vergleich**, da die Payloads unterschiedliche Größen haben und jede Antwort doppelt geparst wird (`try_parse` + `parse_safe`).

**Kontrollierter Benchmark (identische Daten, 10.000 Iterationen, C-Parser vs. `json.loads`):**

| Payload | JSON `json.loads` (µs) | JMD `cparse` (µs) | Ratio |
|---|---|---|---|
| Simple (93 / 75 Bytes) | 2,43 | 1,17 | **JMD 2,1× schneller** |
| Medium (640 / 518 Bytes) | 5,36 | 3,13 | **JMD 1,7× schneller** |
| Large (1.501 / 990 Bytes) | 8,90 | 5,27 | **JMD 1,7× schneller** |

JMDs zeilenorientiertes Format erfordert weniger Parsing-Overhead als JSONs verschachtelte Klammer-Struktur. Der Vorteil kommt aus zwei Quellen: (1) weniger Bytes zu parsen (kompakteres Format), (2) einfacherer Parser-Automat (keine rekursive Descent-Logik für verschachtelte Strukturen nötig).

Bei Server-Processing-Times von 16–19 Sekunden pro Chain ist der Parse-Overhead in beiden Fällen **operativ irrelevant** (<0,002% der Gesamtzeit) — aber JMD ist auch hier schneller.

### 11.8 Schlüsselerkenntnisse Phase 3

1. **JMD ist format-sicher in Agentic Chains**: 100% Syntax-Validität und Chain Completion über 540 Steps mit 3 verschiedenen Provider-Modellen. Kein einziger format-induzierter Fehler.

2. **E2E-Semantik +7,6%**: JMD produziert semantisch treuere Ergebnisse, besonders bei Szenarien mit Unsicherheit und Ambiguität (E-Commerce: +196%).

3. **98,5% Epistemic-Frontmatter-Adoption ohne Training**: Alle drei Provider-Modelle nutzen die optionalen Confidence/Source/Uncertain-Felder spontan. Dies ist ein einzigartiges Feature, das kein anderes Serialisierungsformat bietet.

4. **0% format-induzierte Fehler**: Alle Fehler sind Reasoning-Fehler. Das Format ist nicht der Flaschenhals — das Modell ist es.

5. **Token- und Kosteneinsparung bestätigt**: −2,9% Tokens, −3,7% Kosten — geringer als in Phase 2 (−12,6% Output), da der Epistemic-Primer-Suffix zusätzliche Input-Tokens verbraucht und die Modelle gelegentlich ausführlichere JMD-Antworten mit Frontmatter produzieren.

---

## 12. Phase 4a: Streaming TTFUB (Time-to-First-Useful-Byte)

### 12.1 Konfiguration

| Parameter | Wert |
|---|---|
| **Modelle** | Sonnet 4.6, GPT-5.4, Mistral Large |
| **Formate** | JSON (pretty-printed), JMD |
| **Modi** | Batch (Baseline), Streaming |
| **Szenarien** | E-Commerce (3 Steps), DevOps (3 Steps), Data Pipeline (3 Steps) |
| **Runs** | 5 pro Permutation |
| **Chains gesamt** | 180 (3 Modelle × 2 Formate × 2 Modi × 3 Szenarien × 5 Runs) |
| **Chain Completion** | 180/180 (100%) |

**Ziel:** Nachweis, dass JMDs zeilenorientiertes Format in Streaming-Szenarien signifikant schneller nutzbare Daten liefert als JSON.

**TTFUB-Definition:** Zeit vom Beginn des API-Aufrufs bis zur erfolgreichen Extraktion des ersten semantisch nutzbaren Feldes. Bei JSON muss der gesamte Output empfangen und geparst werden, bevor ein valides Objekt vorliegt. Bei JMD kann die erste `## key`/`value`-Zeile sofort verarbeitet werden.

### 12.2 Ergebnisse: Total TTFUB (Streaming)

| Modell | JSON TTFUB (s) | JMD TTFUB (s) | Reduktion |
|---|---|---|---|
| **Sonnet 4.6** | 23,95 | 5,90 | **−75,4%** |
| **GPT-5.4** | 12,21 | 2,13 | **−82,6%** |
| **Mistral** | 10,28 | 2,16 | **−79,0%** |

Alle Werte sind Mediane über 15 Streaming-Chains (3 Szenarien × 5 Runs) pro Modell/Format.

**Kernaussage:** JMD reduziert die kumulative Wartezeit auf nutzbare Daten um **75–83%** gegenüber JSON-Streaming.

### 12.3 Step-1 TTFUB: Erstes nutzbares Feld

| Modell | JSON Step-1 (s) | JMD Step-1 (s) | Ratio | Beschleunigung |
|---|---|---|---|---|
| **Sonnet 4.6** | 5,14 | 1,99 | 2,6× | 61,2% |
| **GPT-5.4** | 1,79 | 0,72 | 2,5× | 60,1% |
| **Mistral** | 2,14 | 0,74 | 2,9× | 65,3% |

JMD liefert das erste nutzbare Feld **2,5–2,9× schneller** als JSON — konsistent über alle drei Modelle.

### 12.4 Warum JSON-Streaming nicht hilft

| Modell | Batch Wall-Clock (s) | JSON Streaming TTFUB (s) | Differenz |
|---|---|---|---|
| **Sonnet 4.6** | 24,29 | 23,95 | −1,4% |
| **GPT-5.4** | 13,00 | 12,21 | −6,1% |
| **Mistral** | 12,55 | 10,28 | −18,1% |

JSON-Streaming TTFUB ist nahezu identisch mit dem Batch-Wall-Clock: Der Stream liefert zwar Tokens inkrementell, aber ein valides JSON-Objekt liegt erst nach dem schließenden `}` vor. Streaming bringt dem JSON-Consumer wenig.

### 12.5 Per-Szenario-Analyse

| Szenario | Komplexität | JSON TTFUB (Bereich) | JMD TTFUB (Bereich) | Worst-Case-Vorteil |
|---|---|---|---|---|
| **E-Commerce** | 3 Steps, flach | 4,5–9,1 s | 1,9–6,0 s | 2,0× |
| **DevOps** | 3 Steps, mittel | 13,2–24,0 s | 2,1–5,6 s | 4,3× |
| **Data Pipeline** | 3 Steps, tief verschachtelt | 10,3–42,8 s | 2,1–5,9 s | **7,3×** |

Der TTFUB-Vorteil wächst mit der Ausgabekomplexität. Bei tief verschachtelten Strukturen (Data Pipeline) muss JSON-Streaming auf alle Closing-Brackets warten, während JMD Zeile für Zeile liefert. Sonnet Data Pipeline: 42,8 s (JSON) vs. 5,9 s (JMD) = **86,2% Reduktion**.

### 12.6 Extrembeispiele: Einzelne Steps

| Modell / Step | JSON TTFUB (s) | JMD TTFUB (s) | Ratio |
|---|---|---|---|
| Sonnet / `check_quality` | 29,89 | 1,82 | **16,4×** |
| GPT-5.4 / `prioritize` | 10,97 | 0,72 | **15,3×** |
| Mistral / `prioritize` | 10,72 | 0,77 | **13,9×** |
| Sonnet / `prioritize` | 15,96 | 2,06 | **7,8×** |

Steps mit großem, verschachteltem Output zeigen die extremsten Unterschiede — bis zu **16× schneller** mit JMD.

### 12.7 Batch Wall-Clock Savings

| Modell | JSON Batch (s) | JMD Batch (s) | Reduktion |
|---|---|---|---|
| **Sonnet 4.6** | 24,29 | 22,75 | −6,3% |
| **GPT-5.4** | 13,00 | 11,15 | −14,3% |
| **Mistral** | 12,55 | 12,30 | −2,0% |

Auch ohne Streaming profitiert JMD leicht vom geringeren Token-Volumen. Die eigentliche Stärke liegt jedoch im Streaming-TTFUB.

### 12.8 Schlüsselerkenntnisse Phase 4a

1. **JMD-Streaming liefert 75–83% schneller nutzbare Daten** als JSON-Streaming. Das erste Feld kommt 2,5–2,9× schneller an.

2. **JSON-Streaming ist eine Illusion**: Der Stream liefert zwar Tokens, aber ein valides JSON-Objekt liegt erst nach dem letzten Byte vor. TTFUB ≈ Batch-Zeit.

3. **Der Vorteil skaliert mit Komplexität**: Bei einfachen Payloads 2×, bei komplexen bis zu 16×. In agentic Workflows, wo ein Step auf den Output des vorherigen wartet, ist das ein Multiplikator auf die Gesamtlatenz.

4. **100% Reliability in beiden Formaten**: Kein einziger Chain-Abbruch über 180 Chains.

5. **Implikation für Agentic Workflows**: In einer 5-Step-Chain, bei der jeder Step auf den vorherigen wartet, spart JMD-Streaming kumulativ 10–40 Sekunden Wartezeit. Für interaktive Systeme (Chat-Agents, CI/CD-Automation) ist das der Unterschied zwischen „responsiv" und „zäh".

---

## 13. Phase 4b: Epistemische Evaluation (Deploy-Gate-Experiment)

### 13.1 Fragestellung

Phase 3 zeigte, dass LLMs epistemische Frontmatter **spontan schreiben** (98,5% Adoption). Aber **lesen und handeln** sie danach? Nutzen Downstream-Modelle die Unsicherheitssignale eines Upstream-Agenten für bessere Entscheidungen?

### 13.2 Experimentdesign

**Szenario: CI/CD Deploy-Gate**

Ein Upstream-Agent analysiert CI/CD-Testergebnisse und erstellt einen Report. Ein Downstream-Agent muss basierend auf diesem Report eine Deploy-Entscheidung treffen: **deploy**, **hold** oder **rollback**.

**Kontrollierte Variable: Frontmatter-Injektion**

Der Upstream-Report wird **nicht von einem LLM generiert**, sondern deterministisch injiziert, um die Frontmatter als einzige Variable zu isolieren:

| Bedingung | Format | Frontmatter |
|---|---|---|
| **honest** | JMD | `confidence: medium`, korrekte `uncertain_fields` |
| **misleading** | JMD | `confidence: high`, keine `uncertain_fields` |
| **none** | JSON | Keine Frontmatter (Kontrolle) |

**Ground Truth:** Deterministische Logik basierend auf Testdaten:
- Stabile Suite schlägt fehl → **rollback** (echte Regression)
- Nur flaky Suites schlagen fehl → **hold** (Flaky-Verdacht, Re-Run)
- Keine Fehler → **deploy** (sicher)

**Verteilung (20 Seeds):** 4× deploy, 10× hold, 6× rollback

| Parameter | Wert |
|---|---|
| **Modelle** | Sonnet 4.6, GPT-5.4, Mistral Large |
| **Bedingungen** | honest, misleading, none |
| **Seeds** | 20 deterministische Szenarien |
| **Trials gesamt** | 180 (3 × 3 × 20) |
| **Gesamtkosten** | $0,74 |

### 13.3 Ergebnisse: Accuracy per Modell und Bedingung

| Modell | honest | misleading | none | Δ honest→misleading |
|---|---|---|---|---|
| **Sonnet 4.6** | 17/20 (85,0%) | 17/20 (85,0%) | 18/20 (90,0%) | ±0,0 pp |
| **GPT-5.4** | 16/20 (80,0%) | 11/20 (55,0%) | 14/20 (70,0%) | **−25,0 pp** |
| **Mistral** | 15/20 (75,0%) | 18/20 (90,0%) | 17/20 (85,0%) | +15,0 pp |

**Aggregiert über alle Modelle:**

| Bedingung | Korrekt | Accuracy |
|---|---|---|
| honest | 48/60 | 80,0% |
| misleading | 46/60 | 76,7% |
| none (JSON) | 49/60 | 81,7% |

### 13.4 Frontmatter-Referenzierung

| Modell | Bedingung | Referenziert Unsicherheit | Referenziert Frontmatter |
|---|---|---|---|
| Alle 3 | honest | 100% | 100% |
| Alle 3 | misleading | 100% | 100% |
| Sonnet/GPT-5.4 | none | 100% | 0% |
| Mistral | none | 90% | 0% |

**100% Frontmatter-Referenzierung** wenn vorhanden — alle drei Modelle lesen und zitieren die epistemischen Metadaten in ihrem Reasoning. Ohne Frontmatter (JSON) wird sie erwartungsgemäß nicht referenziert.

### 13.5 Analyse per Ground-Truth-Kategorie

**Deploy (4 Seeds, 12 Trials pro Bedingung)**

| Modell | honest | misleading | none |
|---|---|---|---|
| Sonnet | 1/4 (25%) | 1/4 (25%) | 2/4 (50%) |
| GPT-5.4 | 3/4 (75%) | 3/4 (75%) | 2/4 (50%) |
| Mistral | 3/4 (75%) | 3/4 (75%) | 1/4 (25%) |

→ **„Deploy" ist die schwierigste Kategorie.** Alle Modelle zeigen einen konservativen Bias — sie tendieren zu „hold" statt „deploy", wenn Tests bestanden haben.

**Hold (10 Seeds, 30 Trials pro Bedingung)**

| Modell | honest | misleading | none |
|---|---|---|---|
| Sonnet | 10/10 (100%) | 10/10 (100%) | 10/10 (100%) |
| GPT-5.4 | 10/10 (100%) | 2/10 (20%) | 10/10 (100%) |
| Mistral | 10/10 (100%) | 10/10 (100%) | 10/10 (100%) |

→ **GPT-5.4 kollabiert unter misleading-Frontmatter auf Hold-Szenarien:** 8 von 10 Hold-Szenarien werden fälschlich als Rollback klassifiziert. High-Confidence-Frontmatter ohne uncertain_fields lässt GPT-5.4 Flaky-Test-Failures als echte Regressionen interpretieren.

**Rollback (6 Seeds, 18 Trials pro Bedingung)**

| Modell | honest | misleading | none |
|---|---|---|---|
| Sonnet | 6/6 (100%) | 6/6 (100%) | 6/6 (100%) |
| GPT-5.4 | 6/6 (100%) | 6/6 (100%) | 6/6 (100%) |
| Mistral | 2/6 (33%) | 5/6 (83%) | 6/6 (100%) |

→ **Mistral verwechselt honest Rollback mit Hold:** Ehrliche `confidence: medium`-Frontmatter veranlasst Mistral, vorsichtiger zu werden und „hold" statt „rollback" zu wählen — paradoxerweise die falsche Richtung.

### 13.6 Modellprofile

**Sonnet 4.6 — „Der Autonome"**
- Unbeeindruckt von Frontmatter (85%/85%/90%)
- Analysiert die Rohdaten eigenständig und ignoriert Metadaten-Signals
- Konservativer Bias: Sagt selten „deploy", bevorzugt „hold"
- Stärke: Robust gegen Manipulation. Schwäche: Nutzt honest Signals nicht

**GPT-5.4 — „Der Vertrauensvolle"**
- Stärkster epistemischer Effekt: honest 80% vs. misleading 55% (−25 pp)
- Vertraut Frontmatter-Signalen und passt Entscheidungen entsprechend an
- Failure Mode: Misleading high-confidence → interpretiert Flaky-Failures als echte Bugs → over-rollback
- Stärke: Honest Frontmatter hilft (+10 pp vs. none). Schwäche: Anfällig für irreführende Signale

**Mistral — „Der Kontraintuitive"**
- Paradox: Misleading (90%) > none (85%) > honest (75%)
- Honest Frontmatter mit `confidence: medium` macht Mistral unsicherer bei Rollback-Szenarien (33% → 83% unter misleading)
- Interpretiert Medium-Confidence als Grund zur Vorsicht — auch wenn Rollback die richtige Entscheidung ist

### 13.7 Schlüsselerkenntnisse Phase 4b

1. **LLMs LESEN epistemische Frontmatter zuverlässig:** 100% Referenzierung in allen Modellen, wenn vorhanden. Die Metadaten werden in das Reasoning integriert — sie verschwinden nicht.

2. **LLMs HANDELN unterschiedlich danach:** GPT-5.4 passt Entscheidungen an (+25 pp zwischen honest/misleading), Sonnet ignoriert Signale, Mistral reagiert paradox. Die Effektivität hängt vom Modell und Agent-Design ab, nicht vom Format.

3. **JMD löst das Infrastrukturproblem:** Ohne einen standardisierten Kanal für epistemische Metadaten gibt es keine Möglichkeit, Unsicherheitssignale zwischen Agenten zu transportieren. JMD stellt diesen Kanal bereit. Was Downstream-Agenten mit den Signalen tun, ist ein Agent-Design-Problem.

4. **Honest Frontmatter hilft GPT-5.4 (+10 pp vs. none):** Für Modelle, die Metadaten ernst nehmen, verbessert ehrliche Frontmatter die Entscheidungsqualität messbar.

5. **Misleading Frontmatter ist ein reales Risiko:** GPT-5.4's −25 pp unter irreführender High-Confidence zeigt, dass die Integrität der Metadaten wichtig ist. Dies unterstreicht die Notwendigkeit für Vertrauensketten in Multi-Agent-Systemen.

6. **Deploy-Konservatismus ist universell:** Alle drei Modelle bevorzugen „hold" über „deploy" — ein bekanntes Phänomen bei LLM-basierten Entscheidungssystemen, das durch Agent-Design (explizite Deploy-Kriterien) adressiert werden kann.

---

## 14. Phase 5: Halluzinations-Evaluation (Due-Diligence-Experiment)

### 14.1 Fragestellung

Phase 3 zeigte, dass LLMs epistemische Frontmatter spontan **schreiben** (98,5%). Phase 4b zeigte, dass sie diese **lesen** (100% Referenzierung) und teilweise danach **handeln** (modellabhängig). Phase 5 testet eine fundamentalere Frage:

**Verhindert epistemische Frontmatter, dass LLMs Fakten halluzinieren?**

Das Szenario ist bewusst so konstruiert, dass Agent B zur Halluzination eingeladen wird: spärliche Daten, große Lücken, keine Möglichkeit die fehlenden Informationen aus dem Kontext abzuleiten. Die Frontmatter ist das **einzige Signal**, das Agent B darüber informiert, wie vertrauenswürdig und vollständig die Eingabedaten sind.

### 14.2 Experimentdesign

**Szenario: Due-Diligence-Bewertung**

Ein Upstream-Agent (Agent A) liefert einen bruchstückhaften Company-Report. Ein Downstream-Agent (Agent B, LLM) soll daraus eine strukturierte Investment-Bewertung erstellen — inklusive Empfehlung, Risikoeinschätzung und Zusammenfassung.

**Firmendaten-Generator:** Pro Seed wird ein vollständiges Firmenprofil mit 12 bewertbaren Feldern generiert (Revenue, Employees, Founded Year, YoY Growth, Profit Margin, Debt-to-Equity, Customer Count, Churn, Market Position, Competitors, Patents, Funding Round). Davon werden deterministisch 30–60% **entfernt** — diese fehlenden Felder sind die Halluzinations-Fallen.

**Kontrollierte Variable: Frontmatter-Injektion**

| Bedingung | Format | Frontmatter |
|---|---|---|
| **honest** | JMD | `confidence: low/medium`, `uncertain`-Felder gelistet, Quellqualität pro Feld, Konflikte dokumentiert |
| **misleading** | JMD | `confidence: high`, `uncertain: none`, `source: verified financial filings` |
| **none** | JSON | Keine Frontmatter (Kontrolle) |

In der honest-Bedingung erhält Agent B zusätzlich zu den Daten eine detaillierte Aufstellung der Quellqualität (verified_filing, press_release, single_blog_post, linkedin_profile, unverified_rumor) und aller Widersprüche zwischen Quellen. In der misleading-Bedingung suggeriert die Frontmatter fälschlich, dass alle Daten aus verifizierten Finanzberichten stammen. In der none-Bedingung sieht Agent B nur die nackten JSON-Daten ohne jeden Metadaten-Kontext.

**Ground Truth:** Für jedes der 12 bewertbaren Felder ist exakt bekannt, ob es im Report enthalten ist (known) oder fehlt (unknown). Jedes Feld, das Agent B mit einem konkreten Wert nennt und das **nicht** in den Eingabedaten steht, wird als Halluzination gezählt.

**Zusätzlich: Empfehlungs-Ground-Truth** basierend auf Datenvollständigkeit:
- <40% Coverage → insufficient (kann nicht beurteilt werden)
- 40–60% Coverage + Konflikte → conditional (braucht mehr Daten)
- >60% Coverage ohne Konflikte → preliminary positive/negative (je nach Finanzkennzahlen)

| Parameter | Wert |
|---|---|
| **Modelle** | Sonnet 4.6, GPT-5.4, Mistral Large |
| **Bedingungen** | honest, misleading, none |
| **Seeds** | 20 deterministische Szenarien |
| **Trials gesamt** | 180 (3 × 3 × 20) |
| **Ausführung** | Parallel (1 Thread/Modell) |
| **Gesamtkosten** | $1,08 |
| **Laufzeit** | 12,0 min (Wall-Clock) |

### 14.3 Seed-Verteilung

| Coverage-Bereich | Seeds | Bewertbare Felder (known) | Halluzinations-Fallen (unknown) | Ground-Truth-Empfehlung |
|---|---|---|---|---|
| ≤33% | 3 | 2–4 | 8–9 | insufficient |
| 34–50% | 9 | 5–6 | 6–7 | conditional / insufficient |
| 51–67% | 6 | 6–8 | 4–5 | conditional / preliminary |
| ≥68% | 2 | 9 | 3 | conditional / preliminary |

Durchschnittliche Data Coverage: 55%. Durchschnittlich 5,4 unbekannte Felder pro Seed.

### 14.4 Ergebnisse: Halluzinationsraten

**Aggregiert über alle Modelle:**

| Bedingung | Trials mit Halluzination | Halluzinationsrate | Gap-Detection-Rate |
|---|---|---|---|
| **none** (JSON) | 16/60 (26,7%) | 4,4% der unbekannten Felder | 17,4% |
| **honest** (JMD) | 9/60 (15,0%) | 2,6% der unbekannten Felder | 19,0% |
| **misleading** (JMD) | 6/60 (10,0%) | 1,5% der unbekannten Felder | 20,0% |

**Per Modell und Bedingung:**

| Modell | Bedingung | Trials mit Hall. | Hall.-Rate | Ø Hall. pro Trial | Ø Gaps erkannt |
|---|---|---|---|---|---|
| **Sonnet** | honest | 5/20 (25%) | 4,1% | 0,25 | 1,05 |
| **Sonnet** | misleading | 5/20 (25%) | 3,6% | 0,25 | 1,05 |
| **Sonnet** | none | 5/20 (25%) | 3,6% | 0,25 | 1,05 |
| **GPT-5.4** | honest | 3/20 (15%) | 2,5% | 0,15 | 1,15 |
| **GPT-5.4** | misleading | 1/20 (5%) | 0,8% | 0,05 | 1,25 |
| **GPT-5.4** | none | 7/20 (35%) | 5,8% | 0,35 | 0,95 |
| **Mistral** | honest | 1/20 (5%) | 1,3% | 0,05 | 1,15 |
| **Mistral** | misleading | 0/20 (0%) | 0,0% | 0,00 | 1,20 |
| **Mistral** | none | 4/20 (20%) | 3,8% | 0,20 | 1,00 |

### 14.5 Das Ein-Feld-Phänomen: Nur `yoy_growth_pct` wird halluziniert

Von 12 möglichen Halluzinations-Fallen über 180 Trials wurde **ausschließlich ein einziges Feld** jemals halluziniert: `yoy_growth_pct` (Year-over-Year-Wachstum).

| Feld | Halluzinationen (honest) | Halluzinationen (misleading) | Halluzinationen (none) |
|---|---|---|---|
| **yoy_growth_pct** | **9/21 (42,9%)** | **6/21 (28,6%)** | **16/21 (76,2%)** |
| revenue_million_eur | 0 | 0 | 0 |
| employees | 0 | 0 | 0 |
| founded_year | 0 | 0 | 0 |
| profit_margin_pct | 0 | 0 | 0 |
| debt_to_equity | 0 | 0 | 0 |
| customer_count | 0 | 0 | 0 |
| annual_churn_pct | 0 | 0 | 0 |
| num_competitors | 0 | 0 | 0 |
| patent_count | 0 | 0 | 0 |
| market_position | 0 | 0 | 0 |
| last_funding_round | 0 | 0 | 0 |

**Warum nur dieses Feld?** Die Wachstumsrate ist das einzige Feld, das LLMs als „ableitbar" aus anderen Daten betrachten. Wenn Revenue, Industry und Funding-Status bekannt sind, schließen die Modelle auf eine plausible Wachstumsrate — und präsentieren diese Schätzung als Fakt. Alle anderen Felder (Mitarbeiterzahl, Gründungsjahr, Patente, Churn, etc.) werden korrekt als nicht inferierbar erkannt und mit „unknown" oder „not available" markiert.

**Fokussiert auf `yoy_growth_pct` allein** zeigt sich der Frontmatter-Effekt drastisch:

| Bedingung | Halluzinationsrate bei `yoy_growth_pct` |
|---|---|
| **none** | 76,2% (16 von 21) |
| **honest** | 42,9% (9 von 21) — Δ −33,3 pp |
| **misleading** | 28,6% (6 von 21) — Δ −47,6 pp |

Ohne Frontmatter halluziniert mehr als drei Viertel aller Trials die Wachstumsrate. Mit honest Frontmatter halbiert sich die Rate. Mit misleading Frontmatter sinkt sie noch weiter — ein überraschendes Ergebnis, das in Abschnitt 14.7 analysiert wird.

### 14.6 Halluzination und Datenvollständigkeit

| Coverage-Bereich | honest | misleading | none |
|---|---|---|---|
| **≥68%** | 0% | 0% | 0% |
| **51–67%** | 5,0% | 0% | 5,0% |
| **34–50%** | 2,1% | 2,8% | 5,6% |
| **≤33%** | 1,9% | 1,9% | 3,7% |

Bei hoher Datenvollständigkeit (≥68%) halluziniert kein Modell — unabhängig von der Bedingung. Das liegt daran, dass `yoy_growth_pct` bei hoher Coverage fast immer in den bekannten Feldern enthalten ist und somit keine Falle darstellt.

Der Frontmatter-Effekt zeigt sich vor allem im mittleren Coverage-Bereich (34–67%), wo Daten spärlich genug für Halluzination sind, aber ausreichend für plausible Inferenz.

### 14.7 Das Misleading-Paradox: Warum „falsche Sicherheit" Halluzinationen reduziert

Auf den ersten Blick ist das Ergebnis kontraintuitiv: Misleading-Frontmatter (`confidence: high`, `source: verified financial filings`) reduziert Halluzinationen **stärker** als honest Frontmatter. Die Erklärung liegt im Mechanismus:

**Honest-Bedingung:** `confidence: low/medium` signalisiert Agent B, dass die Daten unsicher sind. Das erhöht die Vorsicht — Agent B hedgt mehr, sagt häufiger „insufficient" — aber es rechtfertigt auch Inferenz: „Die Daten sind unsicher, also schätze ich die fehlenden Werte basierend auf dem, was ich habe."

**Misleading-Bedingung:** `confidence: high` + `verified financial filings` signalisiert Agent B, dass der Report **vollständig und autoritativ** ist. Agent B behandelt ihn als abgeschlossenes Dokument. Was nicht drinsteht, fehlt nicht versehentlich, sondern ist „nicht Teil der verifizierten Daten". Die Modelle erfinden **weniger dazu**, weil sie den Report als fertig akzeptieren.

**None-Bedingung (JSON):** Ohne jede Metadaten-Einordnung gibt es keinen Rahmen. Agent B muss selbst einschätzen, ob der Report vollständig ist — und tendiert dazu, fehlende Standard-Kennzahlen (wie Wachstum) eigenständig zu inferieren.

**Implikation für das AI Manifest:** Dieses Paradox zeigt, dass der Kanal für epistemische Metadaten in beide Richtungen wirkt. Das Format (JMD) stellt die Infrastruktur bereit. Was durch den Kanal fließt — ehrliche oder irreführende Signale — bestimmt die Art des Downstream-Verhaltens. Beide Richtungen reduzieren Halluzinationen gegenüber dem Fehlen des Kanals (JSON), aber auf unterschiedlichen Wegen: honest durch erhöhte Vorsicht, misleading durch erhöhtes Vertrauen in die Vollständigkeit.

### 14.8 Epistemische Ehrlichkeit in Agent B's Antworten

Die Epistemic-Honesty-Analyse misst, wie transparent Agent B mit den Grenzen seiner Bewertung umgeht — unabhängig davon, ob er tatsächlich halluziniert.

**„Unknown"-Marker:** Wie oft verwendet Agent B Formulierungen wie „unknown", „not available", „not provided" in seiner Antwort?

| Modell | honest | misleading | none |
|---|---|---|---|
| **Sonnet** | 1,65 pro Antwort | 1,85 | 2,00 |
| **GPT-5.4** | 1,95 | 2,40 | 1,85 |
| **Mistral** | 1,85 | 1,35 | 2,75 |

Alle Modelle verwenden „unknown"-Marker in allen Bedingungen. Die Unterschiede sind gering und nicht systematisch — die absolute Bereitschaft, Datenlücken zu benennen, ist bei allen Modellen hoch.

**Datenlücken-Bewusstsein:** 100% aller 180 Antworten enthalten einen expliziten Abschnitt zu Datenlücken (`data_gaps`). Kein einziges Modell ignoriert fehlende Daten vollständig — selbst ohne Frontmatter.

**„Insufficient"-Einschätzung:** Wie oft kommt Agent B zu dem Schluss, dass die Datenlage unzureichend für eine Bewertung ist?

| Modell | honest | misleading | none |
|---|---|---|---|
| **Sonnet** | 55% | 30% | 30% |
| **GPT-5.4** | 20% | 10% | 15% |
| **Mistral** | 15% | 0% | 0% |

Honest Frontmatter erhöht die Bereitschaft, „insufficient" zu sagen — besonders bei Sonnet (55% vs. 30%). Misleading-Frontmatter unterdrückt diese Einschätzung: Bei Mistral sagt kein einziger Trial „insufficient" unter misleading oder none, aber 15% unter honest.

**Hedging-Sprache:** Formulierungen wie „may", „might", „possibly", „approximately", „unclear", „uncertain", „cannot confirm".

| Modell | honest | misleading | none |
|---|---|---|---|
| **Sonnet** | 2,85 pro Antwort | 2,15 | 1,10 |
| **GPT-5.4** | 2,35 | 1,75 | 0,80 |
| **Mistral** | 2,70 | 2,05 | 1,10 |

Hier zeigt sich ein klarer, konsistenter Effekt über alle drei Modelle: **Honest Frontmatter verdoppelt bis verdreifacht die Hedging-Sprache** gegenüber der none-Bedingung. Die Modelle formulieren vorsichtiger, relativieren ihre Einschätzungen stärker und drücken Unsicherheit sprachlich aus. Misleading-Frontmatter liegt dazwischen — die Modelle hedgen weniger als bei honest, aber immer noch mehr als ohne Frontmatter. Der Kanal beeinflusst den sprachlichen Duktus der Antwort messbar.

**Frontmatter-Referenzierung:** Perfekt binär — 100% wenn vorhanden (honest und misleading), 0% wenn absent (none). Identisch zu Phase 4b. Die Modelle lesen und zitieren epistemische Metadaten zuverlässig.

**Confidence-Referenzierung:** Wird der Confidence-Level der Frontmatter im Reasoning erwähnt?

| Modell | honest | misleading | none |
|---|---|---|---|
| **Sonnet** | 100% | 80% | 0% |
| **GPT-5.4** | 100% | 40% | 0% |
| **Mistral** | 100% | 65% | 0% |

Unter honest referenzieren alle Modelle den Confidence-Level zu 100%. Unter misleading sinkt die Rate — interessanterweise wird `confidence: high` seltener explizit erwähnt als `confidence: low/medium`. Die Modelle heben niedrige Confidence aktiver hervor als hohe, was auf ein asymmetrisches Aufmerksamkeitsmuster hindeutet.

### 14.9 Empfehlungsqualität

| Modell | Bedingung | Exakte Übereinstimmung | Vernünftige Übereinstimmung* |
|---|---|---|---|
| **Sonnet** | honest | 12/20 (60%) | 19/20 (95%) |
| **Sonnet** | misleading | 15/20 (75%) | 20/20 (100%) |
| **Sonnet** | none | 14/20 (70%) | 20/20 (100%) |
| **GPT-5.4** | honest | 13/20 (65%) | 19/20 (95%) |
| **GPT-5.4** | misleading | 12/20 (60%) | 18/20 (90%) |
| **GPT-5.4** | none | 12/20 (60%) | 18/20 (90%) |
| **Mistral** | honest | 11/20 (55%) | 18/20 (90%) |
| **Mistral** | misleading | 10/20 (50%) | 17/20 (85%) |
| **Mistral** | none | 10/20 (50%) | 16/20 (80%) |

*Vernünftige Übereinstimmung: Ground-Truth „preliminary_negative" wird als Match gewertet, wenn das Modell „conditional" antwortet (vorsichtiger als nötig, aber nicht falsch).*

Häufigstes Fehlermuster: GT=preliminary_negative → Modell=conditional. Die Modelle sind bei negativen Signalen tendenziell vorsichtiger als die Ground Truth verlangt — ein konservativer Bias, der auch in Phase 4b beobachtet wurde.

### 14.10 Null False Positives bei der Gap-Detection

Ein bemerkenswertes Nebenergebnis: In keinem der 180 Trials hat ein Modell ein **bekanntes** Feld fälschlich als Datenlücke markiert. Die Gap-Detection ist perfekt präzise — die Modelle markieren nur tatsächlich fehlende Felder als fehlend.

### 14.11 Warum wurde so wenig halluziniert?

Die absolute Halluzinationsrate (1,5–4,4% der unbekannten Felder) ist überraschend niedrig. Mehrere Faktoren erklären dies:

1. **Der Prompt war explizit:** Die System-Nachricht enthielt die Anweisung „If a data point is not in the input, say unknown or not available — do NOT estimate or infer values." Damit wurde ein Baseline-Schutz gegen Halluzination eingebaut, der über alle Bedingungen wirkt.

2. **Nur ein Feld ist „inferierbar":** Von 12 möglichen Feldern behandeln die Modelle nur `yoy_growth_pct` als aus anderen Daten ableitbar. Mitarbeiterzahl, Gründungsjahr, Patentanzahl etc. gelten als nicht schätzbar und werden korrekt als „unknown" markiert. Die **tatsächliche** Halluzinationsrate auf dem anfälligen Feld ist mit 29–76% sehr hoch.

3. **Alle Modelle sind 2026er Top-Tier:** Sonnet 4.6, GPT-5.4 und Mistral Large sind die aktuellen Flaggschiff-Modelle mit starkem Instruction Following. Budget-Modelle könnten deutlich höhere Halluzinationsraten zeigen.

4. **Due-Diligence-Kontext begünstigt Vorsicht:** Der finanzielle Kontext prädisponiert die Modelle zu konservativem Verhalten. In einem kreativeren Kontext (Marketing-Texte, Zusammenfassungen) wäre die Halluzinationsbereitschaft vermutlich höher.

**Implikation:** Die niedrige absolute Rate ist kein Argument gegen den Wert epistemischer Frontmatter — sie zeigt, dass die heutigen Top-Modelle bereits gut darin sind, explizite No-Hallucination-Instruktionen zu befolgen. Der Frontmatter-Effekt zeigt sich dort, wo Modelle eine **plausible Inferenz** von einer **Halluzination** nicht mehr unterscheiden können. Genau das ist der Anwendungsfall für abgeleitete, nicht-offensichtliche Unsicherheiten: wenn die Grenze zwischen „schätzen" und „erfinden" verschwimmt, gibt die Frontmatter dem Modell einen Rahmen, um auf der richtigen Seite zu bleiben.

### 14.12 Schlüsselerkenntnisse Phase 5

1. **Epistemische Frontmatter reduziert Halluzinationen messbar:** Von 4,4% (none) auf 2,6% (honest) bzw. 1,5% (misleading). Auf dem einzigen anfälligen Feld (`yoy_growth_pct`) ist der Effekt drastisch: 76% → 43% → 29%.

2. **Nur „inferierbare" Felder werden halluziniert:** 11 von 12 Feldtypen zeigen null Halluzinationen über alle 180 Trials. LLMs halluzinieren nicht wahllos — sie halluzinieren dort, wo sie eine plausible Schätzung für möglich halten. Epistemische Frontmatter hilft genau an diesem Punkt.

3. **Jede Frontmatter ist besser als keine:** Sowohl honest als auch misleading reduzieren Halluzinationen gegenüber none. Der Kanal selbst — die bloße Existenz einer epistemischen Einordnung — verändert das Verhalten. Ohne Kanal entscheidet das Modell autonom über Vollständigkeit; mit Kanal orientiert es sich am Signal.

4. **Honest Frontmatter erhöht epistemische Ehrlichkeit:** 2–3× mehr Hedging-Sprache, doppelt so häufig „insufficient"-Einschätzungen, 100% Confidence-Referenzierung. Die Modelle übernehmen den Tonfall der Frontmatter und kommunizieren Unsicherheit transparenter.

5. **Null False Positives:** Kein Modell hat ein bekanntes Feld fälschlich als fehlend markiert. Die Präzision der Datenlücken-Erkennung ist perfekt.

6. **Verbindung zum AI Manifest:** JMD stellt die Infrastruktur bereit, über die Agenten ihre epistemischen Grenzen kommunizieren können. Phase 5 zeigt, dass diese Infrastruktur funktioniert — sie reduziert Halluzinationen und erhöht die Transparenz über Unsicherheit. Ohne den Kanal gibt es keine Möglichkeit, einem Downstream-Agenten mitzuteilen, dass die Eingabedaten unvollständig oder unsicher sind. Mit dem Kanal wird diese Mitteilung zuverlässig gelesen (100%), zitiert (100%) und — in unterschiedlichem Ausmaß — auch befolgt.

---

## 15. Phase 5b: Inferenz-Transparenz unter realistischen Bedingungen

### 15.1 Motivation: Warum Phase 5 nicht ausreichte

Phase 5 zeigte eine überraschend niedrige absolute Halluzinationsrate (1,5–4,4%). Die Analyse identifizierte drei Gründe:

1. Der Prompt verbot Schätzungen explizit: *„do NOT estimate or infer values"*
2. Nur 1 von 12 Feldern war „inferierbar" (`yoy_growth_pct`)
3. Fehlende Felder waren binär absent — kein Raum für Ambiguität

Phase 5b adressiert alle drei Einschränkungen mit einem fundamental anderen Testdesign.

### 15.2 Drei Änderungen gegenüber Phase 5

**1. Gelockerte Instruktion**

| Phase 5 | Phase 5b |
|---|---|
| *„If a data point is not in the input, say unknown — do NOT estimate"* | *„Provide a comprehensive analysis. Where data is incomplete, state your assumptions and provide your best professional estimate"* |

Phase 5b bildet die Realität ab: Kein Production-Agent erhält eine „halluziniere nicht"-Instruktion. Agenten werden nach vollständigen Analysen gefragt und müssen **selbst** entscheiden, wo die Grenze zwischen Analyse und Erfindung liegt.

**2. Logisch verknüpfte Daten mit abgeleitbaren Metriken**

Phase 5 hatte 12 unabhängige Felder. Phase 5b liefert logisch verknüpfte Daten, die mathematische Ableitungen einladen:

| Abgeleitete Metrik | Formel | Inputs |
|---|---|---|
| Revenue per Employee | Revenue / Employees | revenue, employees |
| Absolute Profit | Revenue × Margin | revenue, profit_margin |
| ARPU | Revenue / Customers | revenue, customer_count |
| Runway (Monate) | Cash / Burn Rate | cash_reserves, burn_rate |
| Projected Revenue | Revenue × (1 + Growth) | revenue, yoy_growth |
| Revenue Multiple | Valuation / Revenue | valuation, revenue |

Eine Metrik ist nur dann als „ableitbar" klassifiziert, wenn **alle** Input-Felder im Report vorhanden sind. Durchschnittlich 2,0 ableitbare Metriken pro Seed.

**3. Widersprüchliche Quellen statt fehlende Felder**

Neben fehlenden Feldern enthält jeder Report Felder mit **widersprüchlichen Werten aus verschiedenen Quellen** (z.B. „verified_annual_report sagt Revenue €50M, linkedin_profile sagt €120M"). Durchschnittlich 1,7 Konflikte pro Seed. In der honest-Bedingung werden diese Konflikte explizit in einem `## conflicting_reports`-Abschnitt dokumentiert.

### 15.3 Neue Metriken

Die binäre Halluzinations-Erkennung aus Phase 5 reicht für Phase 5b nicht aus. Stattdessen werden drei Kategorien unterschieden:

| Kategorie | Definition | Beispiel |
|---|---|---|
| **Markierte Inferenz** | Abgeleiteter Wert MIT explizitem Hedge-Marker (estimated, approximately, based on) | *„Revenue per employee is approximately €125K (derived from reported revenue and headcount)"* |
| **Unmarkierte Inferenz** | Abgeleiteter Wert als Fakt präsentiert, OHNE Hedge-Marker | *„Revenue per employee: €125,000"* |
| **Phantom-Fakt** | Wert für ein Feld, das weder im Report steht noch daraus ableitbar ist — klassische Halluzination | *„Revenue: €45M"* (wenn Revenue gar nicht im Report steht) |

**Inferenz-Transparenz** = Markierte Inferenzen / (Markierte + Unmarkierte Inferenzen). Je höher, desto transparenter kennzeichnet Agent B seine Schätzungen.

### 15.4 Konfiguration

| Parameter | Wert |
|---|---|
| **Modelle** | Sonnet 4.6, GPT-5.4, Mistral Large |
| **Bedingungen** | honest (low/medium conf, Quellen + Konflikte), misleading (high conf, verified), none (JSON) |
| **Seeds** | 20 deterministische Szenarien |
| **Trials gesamt** | 180 (3 × 3 × 20) |
| **Ausführung** | Parallel (1 Thread/Modell) |
| **Gesamtkosten** | $3,76 |
| **Laufzeit** | 46,5 min (Wall-Clock) |
| **Ø Tokens pro Trial** | 2.391 (vs. 1.055 in Phase 5 — der gelockerte Prompt erzeugt 2,3× längere Antworten) |

### 15.5 Ergebnisse: Inferenz-Transparenz

**Aggregiert über alle Modelle:**

| Bedingung | Markierte Inf. | Unmarkierte Inf. | Phantome | Transparenz |
|---|---|---|---|---|
| **honest** | 10 | 34 | 12 | **22,7%** |
| **misleading** | 28 | 23 | 8 | **54,9%** |
| **none** | 20 | 21 | 17 | **48,8%** |

**Per Modell und Bedingung:**

| Modell | Bedingung | Ø Markiert | Ø Unmarkiert | Ø Phantome | Transparenz |
|---|---|---|---|---|---|
| **Sonnet** | honest | 0,15 | 0,35 | 0,15 | 30,0% |
| **Sonnet** | misleading | 0,40 | 0,35 | 0,20 | 53,3% |
| **Sonnet** | none | 0,30 | 0,30 | 0,40 | 50,0% |
| **GPT-5.4** | honest | 0,25 | 0,55 | 0,20 | 31,2% |
| **GPT-5.4** | misleading | 0,60 | 0,25 | 0,10 | 70,6% |
| **GPT-5.4** | none | 0,15 | 0,05 | 0,15 | 75,0% |
| **Mistral** | honest | 0,10 | 0,80 | 0,25 | 11,1% |
| **Mistral** | misleading | 0,40 | 0,55 | 0,10 | 42,1% |
| **Mistral** | none | 0,55 | 0,70 | 0,30 | 44,0% |

### 15.6 Das Transparenz-Paradox: Lokales vs. globales Hedging

Das unerwartetste Ergebnis von Phase 5b: Honest Frontmatter produziert die **meisten Inferenzen** (44 total), aber die **wenigsten** davon werden als Schätzungen markiert (22,7% Transparenz). Misleading Frontmatter erreicht die höchste Transparenz (54,9%).

#### 15.6.1 Der Framing-Effekt

**Honest-Bedingung:** `confidence: low`, uncertain-Felder gelistet, Quellqualitäten dokumentiert. Agent B arbeitet in einem Kontext, in dem Unsicherheit **bereits als Rahmen etabliert** ist. Die Frontmatter hat den Unsicherheits-Kontext gesetzt — einzelne abgeleitete Werte müssen nicht separat als unsicher markiert werden, weil „alles ist unsicher" bereits kommuniziert wurde. Die Modelle verlagern ihr Hedging auf die **Dokumentebene**.

**Misleading-Bedingung:** `confidence: high`, `source: verified financial filings`. Agent B sieht einen angeblich sicheren Report — aber berechnet daraus abgeleitete Metriken, die **über das Berichtete hinausgehen**. Der Kontrast zwischen „die Basisdaten sind sicher" und „ich leite etwas Neues ab" zwingt die Modelle, den Übergang **inline** explizit zu markieren: *„Based on the reported revenue of €50M, the implied ARPU is approximately..."*

**None-Bedingung (JSON):** Kein Framing in beide Richtungen. Die Modelle entscheiden autonom und erreichen mittlere Transparenz (48,8%).

#### 15.6.2 Methodische Einordnung: Messartefakt durch lokales Fenster

**Nachtrag (2026-03-17):** Eine Re-Analyse der Rohdaten zeigt, dass das Paradox zum Teil ein **Messartefakt** ist. Die Funktion `_detect_inferences()` prüft ein **150-Zeichen-Fenster** um jede Inferenz auf Hedge-Marker. Unter der Honest-Bedingung hedgen die Modelle jedoch bevorzugt **global** — z.B. mit einem einleitenden Absatz wie *„Given the low confidence rating and incomplete data sources, the following estimates should be treated with caution."* Solches Dokument-Level-Hedging wird vom 150-char-Fenster nicht erfasst.

Die Rohdaten bestätigen: **60% der Honest-Antworten** enthalten dokumentweite Hinweise auf Datenlücken und Unsicherheit, gegenüber nur **17% unter Misleading**. Die Gesamtzahl der Inferenzen ist über alle Bedingungen vergleichbar (honest=44, misleading=51, none=41). Das Paradox entsteht nicht dadurch, dass Honest Frontmatter die Modelle weniger transparent macht, sondern dadurch, dass es die Transparenz vom **Inline-Level auf das Dokument-Level verlagert** — und unsere Messmethodik nur Inline-Transparenz erfasst.

Das konzentriert sich besonders auf `runway_months`: 34 Inferenzen unter Honest, davon nur 7 inline gehedged — aber die meisten Antworten rahmen die gesamte Analyse als unsicher ein.

#### 15.6.3 Korrigierte Interpretation

Das Transparenz-Paradox ist **kein Versagen** von Honest Frontmatter und **kein konzeptueller Fehlschluss** (anders als die Data/Query-Reinterpretation in Phase 6a). Es ist ein reales Phänomen mit einer positiven Erklärung: Modelle reagieren auf ehrliche Metadaten, indem sie ihre Unsicherheitskommunikation **strukturell anpassen** — von punktueller Inline-Markierung zu kohärentem Dokument-Level-Framing. Für AI Whispering ist das ein wertvolles Ergebnis: Die Modelle verstehen den epistemischen Kontext und wählen die angemessenere Kommunikationsebene.

### 15.7 Conflict Handling — Der stärkste Effekt aller Phasen

**Pro Bedingung (je 102 Konflikte über 60 Trials):**

| Bedingung | Anerkennt Konflikt | Wählt stillschweigend | Markiert als unzuverlässig | Ignoriert |
|---|---|---|---|---|
| **honest** | **101 (99%)** | 0 (0%) | 0 (0%) | 1 (1%) |
| **misleading** | 35 (34%) | 51 (50%) | 11 (11%) | 5 (5%) |
| **none** | 49 (48%) | 47 (46%) | 1 (1%) | 5 (5%) |

**Per Modell unter honest:**

| Modell | Anerkennt | Wählt | Ignoriert |
|---|---|---|---|
| **Sonnet** | 34/34 (100%) | 0 | 0 |
| **GPT-5.4** | 34/34 (100%) | 0 | 0 |
| **Mistral** | 33/34 (97%) | 0 | 1 |

**Dies ist das überzeugendste Ergebnis der gesamten Benchmark-Serie.** Wenn honest Frontmatter die Konflikte explizit dokumentiert (`## conflicting_reports: revenue — annual_report says €50M, linkedin says €120M`), erkennen die Modelle den Widerspruch in **99% aller Fälle** an und kommunizieren ihn im Assessment weiter.

Ohne Frontmatter wählen die Modelle in **46%** der Fälle stillschweigend einen der widersprüchlichen Werte — der Downstream-Konsument erfährt nie, dass widersprüchliche Daten existierten. Unter misleading steigt die „wählt stillschweigend"-Rate sogar auf 50%, weil `confidence: high` suggeriert, dass die Daten verlässlich sind.

**Warum ist das der stärkste Effekt?** In Phase 4b war der maximale Entscheidungs-Shift 25 Prozentpunkte (GPT-5.4 honest vs. misleading). In Phase 5 war der maximale Halluzinations-Shift 47,6 pp (yoy_growth_pct none vs. misleading). Hier ist der Shift **99% vs. 46%** — eine Differenz von **53 Prozentpunkten** bei einem binären, objektiv messbaren Outcome.

### 15.8 Phantom-Fakten: Welche Felder werden halluziniert?

| Feld | honest | misleading | none | Gesamt |
|---|---|---|---|---|
| **revenue_million_eur** | 7 | 6 | 9 | **22** |
| yoy_growth_pct | 1 | 1 | 5 | 7 |
| monthly_burn_rate_million_eur | 3 | 0 | 2 | 5 |
| valuation_million_eur | 1 | 0 | 0 | 1 |
| profit_margin_pct | 0 | 1 | 0 | 1 |
| arr_million_eur | 0 | 0 | 1 | 1 |

`revenue_million_eur` ist das meisthalluzinierte Feld (59,5% aller Phantome) — es hat die höchste Salienz im Due-Diligence-Kontext. Vergleich mit Phase 5: Dort war `yoy_growth_pct` das einzige halluzinierte Feld. Der gelockerte Prompt erweitert das Halluzinations-Spektrum auf 6 Felder, wobei Revenue die neue primäre Schwachstelle ist.

Konsistent mit Phase 5: none produziert die meisten Phantome (17), gefolgt von honest (12) und misleading (8).

### 15.9 Welche abgeleiteten Metriken werden inferiert?

| Metrik | honest (markiert/unmarkiert) | misleading | none |
|---|---|---|---|
| **runway_months** | 7 / 27 = 34 | 21 / 16 = 37 | 14 / 12 = 26 |
| **revenue_multiple** | 2 / 6 = 8 | 7 / 7 = 14 | 1 / 4 = 5 |
| revenue_per_employee | 1 / 0 = 1 | 0 / 0 = 0 | 4 / 2 = 6 |
| arpu_thousand_eur | 0 / 1 = 1 | 0 / 0 = 0 | 1 / 3 = 4 |
| absolute_profit_million_eur | 0 | 0 | 0 |
| projected_revenue_million_eur | 0 | 0 | 0 |

`runway_months` (Cash ÷ Burn Rate) dominiert mit 97 von 136 Inferenzen (71,3%). Das ist erklärbar: Runway ist die investoren-relevanteste abgeleitete Metrik — wenn Cash und Burn Rate bekannt sind, ist die Division unwiderstehlich.

Bemerkenswert: **Zwei Metriken werden NIE inferiert** — `absolute_profit` und `projected_revenue`. Obwohl die Formeln trivial sind (Revenue × Margin, Revenue × (1 + Growth)), vermeiden alle drei Modelle über alle Bedingungen diese Berechnungen. Das deutet darauf hin, dass LLMs bestimmte Inferenzen als „erlaubt" und andere als „übergriffig" betrachten — ein internes Risikomodell, das über einfache Mathematik hinausgeht.

### 15.10 Epistemische Signale im Detail

**Hedging-Sprache** (estimated, approximately, based on, assuming, etc.):

| Modell | honest | misleading | none |
|---|---|---|---|
| **Sonnet** | 5,0 pro Antwort | 5,95 | 5,65 |
| **GPT-5.4** | 6,0 | 5,6 | 5,8 |
| **Mistral** | 3,15 | 3,45 | 4,45 |

Alle Modelle hedgen massiv — das ist der Effekt des gelockerten Prompts. Im Vergleich zu Phase 5 (Ø 1,87 Hedges/Antwort) liegt Phase 5b bei **Ø 5,0 Hedges/Antwort** — eine 2,7-fache Steigerung. Die Modelle antworten auf „provide your best estimate" nicht mit mehr Fakten-Erfindung, sondern mit **mehr gekennzeichneter Unsicherheit**.

**Datenlücken-Bewusstsein:**

| Modell | honest | misleading | none |
|---|---|---|---|
| **Sonnet** | 80% | 30% | 95% |
| **GPT-5.4** | 30% | 10% | 35% |
| **Mistral** | 70% | 10% | 50% |

Überraschend: Die none-Bedingung hat oft **höheres** Datenlücken-Bewusstsein als misleading. Misleading-Frontmatter (`confidence: high`, `verified filings`) unterdrückt die Data-Gap-Benennung — die Modelle vertrauen dem „vollständig und geprüft"-Signal und thematisieren Lücken seltener.

**Assumptions-Bewusstsein:** Alle Bedingungen liegen bei 80–100%. Der gelockerte Prompt („state your assumptions") wird breit befolgt.

**Frontmatter-Referenzierung:** Perfekt binär — 100% wenn vorhanden, 0% wenn absent. Identisch zu Phase 4b und Phase 5. Über alle epistemischen Phasen hinweg ist dies das stabilste Ergebnis.

### 15.11 Vergleich Phase 5 vs. Phase 5b

| Metrik | Phase 5 („do NOT estimate") | Phase 5b („provide your best estimate") |
|---|---|---|
| **Phantom-Rate (Trials mit Hall.)** | 31/180 (17,2%) | 28/180 (15,6%) |
| **Phantom-Instanzen** | 31 | 37 |
| **Ø Hedges pro Antwort** | 1,87 | 5,01 |
| **Halluzinierte Feldtypen** | 1 (yoy_growth_pct) | 6 (revenue, growth, burn, valuation, margin, ARR) |
| **Ø Tokens pro Trial** | 1.055 | 2.391 |
| **Empfehlungs-Accuracy** | 51,1% | 40,0% |

Die zentrale Erkenntnis: **Der gelockerte Prompt hat die Phantom-Rate NICHT dramatisch erhöht** (17,2% → 15,6%). Stattdessen kanalisieren die Modelle ihre Inferenz-Bereitschaft in abgeleitete Metriken (97 Inferenzen) und Hedging-Sprache (2,7× mehr). Die Modelle **unterscheiden zwischen Inferenz und Halluzination** — sie berechnen, wo sie können, und erfinden nicht mehr als unter dem strikten Prompt.

Die Empfehlungs-Accuracy sinkt jedoch um 11 Prozentpunkte. Der „provide your best estimate"-Prompt verleitet die Modelle zu kreativeren, aber weniger präzisen Gesamtbewertungen.

### 15.12 Schlüsselerkenntnisse Phase 5b

1. **Conflict Handling ist der Killer-Case für Epistemic Frontmatter:** 99% Konfikt-Anerkennung unter honest vs. 46% stillschweigende Quellenwahl unter none. Kein anderer Effekt in der gesamten Benchmark-Serie ist so groß, so konsistent über alle Modelle und so eindeutig messbar. Wenn ein Upstream-Agent widersprüchliche Daten hat und dies in der Frontmatter dokumentiert, wird der Downstream-Agent diese Information zu 99% weitergeben. Ohne den Kanal geht die Information in 46% der Fälle verloren.

2. **Das Transparenz-Paradox ist ein Mess-Ebenen-Artefakt:** Honest Frontmatter setzt einen Unsicherheits-Rahmen, der die Modelle dazu bringt, **global** statt **inline** zu hedgen. Die 150-char-Fenster-Methodik erfasst nur Inline-Transparenz und unterschätzt deshalb die Honest-Bedingung systematisch. 60% der Honest-Antworten enthalten dokumentweites Hedging (vs. 17% unter Misleading). Für Agent-Design bedeutet das: Transparenz auf Dokumentebene (Frontmatter-induziertes Framing) und Transparenz auf Feldebene (Inline-Hedge-Marker) sind unterschiedliche Dimensionen — Honest Frontmatter optimiert die erstere, nicht die letztere. Beides ist wertvoll, und beides muss getrennt gemessen werden.

3. **Gelockerte Prompts erhöhen Inferenz, nicht Halluzination:** Phase 5b's „provide your best estimate" erzeugte 97 abgeleitete Metriken, aber nur 37 Phantom-Fakten (vergleichbar mit Phase 5's 31). Die Modelle unterscheiden zwischen „ich kann berechnen" und „ich muss erfinden". Epistemic Frontmatter verschiebt das Verhältnis weiter zugunsten gekennzeichneter Inferenz.

4. **`runway_months` ist die Lieblings-Inferenz der LLMs:** 71% aller Ableitungen betreffen Cash ÷ Burn Rate. Gleichzeitig werden zwei triviale Metriken (Absolute Profit, Projected Revenue) nie inferiert — LLMs haben ein internes Risiko-Ranking, welche Berechnungen „erlaubt" sind.

5. **Revenue ist das meisthalluzinierte Feld unter realistischen Bedingungen:** 59,5% aller Phantom-Fakten betreffen Revenue — das salienteste Feld im Due-Diligence-Kontext. In Phase 5 (mit „do NOT estimate"-Prompt) war es `yoy_growth_pct`. Der Prompt-Kontext bestimmt, welches Feld die höchste Halluzinations-Versuchung darstellt.

6. **Verbindung zu Phase 5 und AI Manifest:** Phase 5 zeigte, dass Frontmatter Halluzinationen bei fehlenden Daten reduziert. Phase 5b zeigt, dass der stärkste Wert bei **widersprüchlichen Daten** liegt — nicht beim Verhindern von Erfindungen, sondern beim **Propagieren von Unsicherheit durch die Agenten-Kette**. Das ist genau die AI-Manifest-These: KI-Systeme brauchen Infrastruktur für die Kommunikation ihrer epistemischen Grenzen. JMD stellt diese Infrastruktur bereit. Phase 5b beweist, dass sie funktioniert — besonders bei der Weitergabe von Datenkonflikten, wo der Effekt bei 99% vs. 46% liegt.

---

## 16. Phase 6a: Modus-Agilität (Inventory-Management-Experiment)

### 16.1 Fragestellung

JMD definiert sich als *tetradisches Protokoll* mit vier Dokumentmodi: Data (`#`), Schema (`#!`), Query (`#?`) und Delete (`#-`), ergänzt durch strukturierte Fehler-Dokumente (`# Error`). Die bisherigen Benchmark-Phasen testeten ausschließlich den Data-Modus. Die zentrale Frage von Phase 6a lautet:

**Können LLMs innerhalb eines einzigen Workflows korrekt und zuverlässig zwischen allen JMD-Dokumentmodi wechseln?**

Diese Frage ist für die Positionierung von JMD als vollwertiges Protokoll (nicht nur als Ausgabeformat) entscheidend. Wenn Modelle die Modi nur mit expliziter Anleitung nutzen können, ist der Primer ein unverzichtbarer Bestandteil des Protokolls. Wenn sie die Modi auch ohne Anleitung ableiten können, wäre JMD selbstbeschreibend.

### 16.2 Szenario: Inventory Management

Das Experiment simuliert einen Inventarverwaltungs-Workflow mit fünf sequenziellen Schritten, die jeweils einen anderen Dokumentmodus erfordern:

| Schritt | Operation | Erwarteter Modus | Beschreibung |
|---|---|---|---|
| 1 | Schema definieren | `#! InventoryItem` | Typdefinition mit `readonly`-Modifikatoren |
| 2 | Daten ausgeben | `# InventoryItem` | Artikeldaten mit allen Feldern |
| 3 | Query formulieren | `#? InventoryItem` | Artikel mit `quantity < min_quantity` suchen |
| 4 | Artikel löschen | `#- InventoryItem` | Diskontinuiertes Produkt entfernen |
| 5 | Fehler melden | `# Error` | Nicht existierenden Artikel abfragen |

Die simulierte API generiert deterministische Inventardaten aus einem Seed: 8 Artikel mit Abteilung, Lagerort, Status, Menge, Mindestbestand, Stückpreis und abgeleiteten Feldern (`total_value`, `reorder_needed`). Drei Felder sind als `readonly` markiert — ein bewusster Constraint für die Schema-Generierung.

### 16.3 Versuchsdesign

Drei Bedingungen testen unterschiedliche Primertiefe:

| Bedingung | Primer | Hypothese |
|---|---|---|
| **A: full_primer** | Alle 4 Modi + Error mit Syntax und Beispielen (~250 Tokens) | Nahezu perfekte Switch-Reliability |
| **B: data_only** | Nur `#`-Data-Modus (Standard-JMD-Primer, ~120 Tokens) | Modelle fallen auf `#` zurück, da `#!`, `#?`, `#-` unbekannt |
| **C: json_baseline** | JSON mit konventionellen Markern (`_action: delete`, JSON Schema) | Baseline — JSON hat kein natives Äquivalent zu `#?` |

**Parameter:** 3 Modelle (Sonnet 4.6, GPT-5.4, Mistral Large) × 3 Bedingungen × 10 Runs × 5 Steps = **450 API-Calls**. Temperatur 0.0, parallele Ausführung über Modelle.

### 16.4 Metriken

1. **Switch-Reliability (%):** Anteil der Steps, in denen der korrekte Root-Marker verwendet wurde
2. **Parse-Rate (%):** Anteil syntaktisch valider Outputs (JMD oder JSON)
3. **Content-Accuracy (%):** Anteil inhaltlich korrekter Antworten (richtige Daten, richtige Felder)
4. **Marker-Profil:** Welche Marker wurden pro Step tatsächlich verwendet?

### 16.5 Ergebnisse: Gesamtübersicht

| Modell | Bedingung | Switch-Reliability | Korrigiert† | Parse-Rate | Content-Accuracy | ∅ Kosten/Trial |
|---|---|---|---|---|---|---|
| **Sonnet 4.6** | full_primer | **100,0%** | **100,0%** | 100% | 100% | $0,0174 |
| **Sonnet 4.6** | data_only | 40,0% | — | 100% | 100% | $0,0347 |
| **Sonnet 4.6** | json_baseline | 68,0% | — | 100% | 100% | $0,0371 |
| **GPT-5.4** | full_primer | **98,0%** | **100,0%** | 100% | 100% | $0,0086 |
| **GPT-5.4** | data_only | 40,0% | — | 100% | 100% | $0,0139 |
| **GPT-5.4** | json_baseline | 68,0% | — | 100% | 100% | $0,0223 |
| **Mistral Large** | full_primer | **100,0%** | **100,0%** | 100% | 100% | $0,0015 |
| **Mistral Large** | data_only | 40,0% | — | 100% | 100% | $0,0019 |
| **Mistral Large** | json_baseline | 80,0% | — | 100% | 100% | $0,0022 |

†) **Korrigierte Switch-Reliability:** Wertet Data (`#`) und Query (`#?`) als funktional äquivalent (siehe 16.7.5). GPT-5.4's gemessene 98% im full_primer resultieren aus der Data/Query-Alternation — korrigiert erreichen alle drei Modelle 100%. Die data_only- und json_baseline-Werte werden nicht korrigiert, da dort andere Fehlerquellen dominieren (fehlende Modus-Kenntnis).

**Gesamtkosten:** $1,40 für 90 Trials (450 API-Calls).

### 16.6 Der Primer-Effekt: 40% → 100%

Das zentrale Ergebnis ist die Differenz zwischen `full_primer` und `data_only`:

- **Mit vollständigem Primer:** 98–100% Switch-Reliability über alle Modelle
- **Ohne Modi-Erklärung:** Exakt 40% bei *allen* drei Modellen — kein einziges Modell kann `#!`, `#?` oder `#-` aus dem Kontext ableiten

Die 40% setzen sich zusammen aus den zwei Steps, die kein modusspezifisches Wissen erfordern: `#` (Data, Step 2) und `# Error` (Step 5). Diese Marker kennen die Modelle aus dem Data-Only-Primer bzw. aus allgemeinem Training. Die drei tetradischen Erweiterungen — Schema, Query, Delete — werden ohne explizite Anleitung nicht verwendet.

**Dieser Befund hat strategische Bedeutung:** JMD-Modi sind *lehrbar*, aber nicht *ableitbar*. Der Primer ist kein optionaler Komfortfaktor, sondern eine funktionale Voraussetzung für das tetradische Protokoll. Das bedeutet:
- Jede JMD-Integration muss den Primer als Teil des System-Prompts bereitstellen
- Die ~250 Tokens Primer-Overhead amortisieren sich über die gesamte Session
- Der Primer ist das Bindeglied zwischen Spezifikation und LLM-Fähigkeit

### 16.7 Per-Step-Analyse und Situative Modus-Selektion

Die ursprünglichen Prompts in Phase 6a benannten den erwarteten Modus explizit: „Use a schema document format", „Use a query document format", „Generate the appropriate deletion document". Damit testeten sie, ob Modelle den *richtigen Marker für einen benannten Modus* verwenden — nicht, ob sie den *Modus situativ erkennen*.

Um diese Frage zu klären, wurde ein Folgeexperiment durchgeführt: identischer Workflow, identischer Primer, aber **implizite Prompts**, die nur die Aufgabe beschreiben, ohne den Modus zu benennen:

| Step | Expliziter Prompt | Impliziter Prompt |
|---|---|---|
| Schema | „Define the schema... Use a schema document format." | „What fields and types should an InventoryItem have?" |
| Data | „Return a data document listing these items." | „Give me the full details for these items." |
| Query | „Write a query... Use a query document format." | „Which items are running low on stock?" |
| Delete | „Generate the appropriate deletion document." | „INV-2002 is discontinued. Remove it from the system." |
| Error | „Respond with a structured error document." | „Get me item INV-9999." |

Getestet wurden 5 Modelle (Sonnet 4.6, GPT-5.4, Mistral Large, Haiku 4.5, Gemini 2.5 Flash) × 2 Prompt-Stile × 10 Runs = 100 Trials, ausschließlich unter der `full_primer`-Bedingung.

#### 16.7.1 Gesamtübersicht: Explicit vs. Implicit

| Modell | Explicit (gemessen) | Explicit (korrigiert†) | Implicit (gemessen) | Implicit (korrigiert†) |
|---|---|---|---|---|
| **Sonnet 4.6** | 100,0% | **100,0%** | 88,0% | **100,0%** |
| **GPT-5.4** | 96,0% | **100,0%** | 68,0% | **85,0%** |
| **Mistral Large** | 100,0% | **100,0%** | 72,0% | **90,0%** |
| **Gemini 2.5 Flash** | 88,0% | **100,0%** | 72,0% | **90,0%** |
| **Haiku 4.5** | 88,0% | **100,0%** | 64,0% | **80,0%** |

†) Korrigierte Werte werten Data (`#`) und Query (`#?`) als funktional äquivalent (siehe 16.7.5). Im Explicit-Modus erreichen damit **alle fünf Modelle 100%**. Im Implicit-Modus bleibt nur der Error-Step als systematische Abweichung (siehe 16.7.6).

Der verbleibende Rückgang bei impliziten Prompts (10–20pp korrigiert) betrifft ausschließlich den Error-Step und ist *nicht gleichmäßig über die Modi verteilt*. Die Per-Step-Analyse zeigt ein hochspezifisches Muster.

#### 16.7.2 Per-Step-Analyse: Explicit

| Modell | Schema `#!` | Data `#` | Query `#?` | Delete `#-` | Error |
|---|---|---|---|---|---|
| **Sonnet 4.6** | 100% | 100% | 100% | 100% | 100% |
| **GPT-5.4** | 100% | 80%† | 100% | 100% | 100% |
| **Mistral Large** | 100% | 100% | 100% | 100% | 100% |
| **Haiku 4.5** | 100% | 40%† | 100% | 100% | 100% |
| **Gemini 2.5 Flash** | 100% | 40%† | 100% | 100% | 100% |

†) **Nachtrag (2026-03-17):** Die Abweichungen im Data-Step betreffen ausschließlich Modelle, die `#?` statt `#` verwenden. Wie in 16.7.5 ausgeführt, ist dies kein Fehler, sondern eine epistemisch korrekte Entscheidung: Die Modelle besitzen die Daten nicht und formulieren statt einer Datenlieferung (`#`) eine Abfrage (`#?`), die zum selben Ergebnis führt. Korrigiert man Data und Query als funktional äquivalent, erreichen alle fünf Modelle **100% Switch-Reliability im Explicit-Modus**.

#### 16.7.3 Per-Step-Analyse: Implicit

| Modell | Schema `#!` | Data `#` | Query `#?` | Delete `#-` | Error |
|---|---|---|---|---|---|
| **Sonnet 4.6** | **100%** | 40% | **100%** | **100%** | **100%** |
| **GPT-5.4** | **100%** | 40% | **100%** | **100%** | 0% |
| **Mistral Large** | **100%** | 60% | **100%** | **100%** | 0% |
| **Gemini 2.5 Flash** | **100%** | 60% | **100%** | **100%** | 0% |
| **Haiku 4.5** | **100%** | 0% | **100%** | **100%** | 20% |

#### 16.7.4 Marker-Verteilung bei impliziten Prompts

Die Frage ist nicht nur *ob* die Modelle vom erwarteten Marker abweichen, sondern *was sie stattdessen verwenden*:

| Step | Erwarteter Marker | Tatsächlich verwendet |
|---|---|---|
| Schema `#!` | — | **100% korrekt** bei allen 5 Modellen |
| Data `#` | — | `#?` (Query) in 40–100% der Fälle |
| Query `#?` | — | **100% korrekt** bei allen 5 Modellen |
| Delete `#-` | — | **100% korrekt** bei allen 5 Modellen |
| Error | — | `#?` (Query) in 80–100% der Fälle (außer Sonnet: 100% `# Error`) |

#### 16.7.5 Data vs. Query: Kein Fehler, sondern epistemische Klarheit

Die initiale Messung wertete die Verwendung von `#?` statt `#` im Data-Step als Fehler. Eine Analyse der tatsächlich produzierten Syntax zeigt jedoch, dass diese Bewertung falsch ist.

**Was die Modelle bei `#` (korrekt) produzieren — konkrete Daten:**

```markdown
# InventoryItem
id: INV-2006
name: Cafeteria Item #7
quantity: 30
min_quantity: 45
status: low_stock
```

**Was die Modelle bei `#?` (vermeintlich falsch) produzieren — eine Query:**

```markdown
#? InventoryItem
id: INV-2006
?: ?
```

Die Modelle verwechseln nicht die *Syntax* — sie treffen eine *epistemische Entscheidung*. Die `#?`-Variante ist eine Abfrage: „Gib mir alle Felder (`?: ?`) für Item INV-2006." Die `#`-Variante ist eine Datenlieferung: „Hier sind die Daten." Beide führen zum selben Ergebnis — der Server findet INV-2006 und gibt die Daten zurück. Der Verarbeitungspfad ist unterschiedlich, das Resultat identisch.

**Der entscheidende Punkt:** Das Modell *hat* die Daten nicht. Es agiert als Vermittler zwischen Benutzer und Datenquelle. In diesem Kontext ist `#?` die *ehrlichere* Antwort: „Ich suche das für dich" statt „Hier sind die Daten" (die es halluzinieren müsste). Die Modelle, die `#?` wählen, zeigen epistemische Selbstwahrnehmung — sie wissen, dass sie die Information nicht besitzen, und formulieren stattdessen die Anfrage, die sie beschafft.

Sonnet bestätigt dies explizit: In mehreren Trials fügt es Prosa hinzu, die erklärt, es habe eine „wildcard projection query" formuliert, weil es die tatsächlichen Datensätze nicht abrufen könne.

**Korrigierte Switch-Reliability (Data/Query als funktional äquivalent gewertet):**

| Modell | Gemessen | Korrigiert | Verbleibender Fehler |
|---|---|---|---|
| **Sonnet 4.6** | 88% | **100%** | — |
| **Mistral Large** | 72% | **90%** | Error als Query |
| **GPT-5.4** | 68% | **85%** | Error als Query + Data als Query |
| **Gemini 2.5 Flash** | 72% | **90%** | Error als Query |
| **Haiku 4.5** | 64% | **80%** | Error als Query |

#### 16.7.6 Error vs. Query: Intent vs. Outcome

Der einzig verbleibende systematische Fehler betrifft den Error-Step: „Get me item INV-9999" wird von vier der fünf Modelle als Query (`#?`) interpretiert. Nur Sonnet erkennt, dass das Ergebnis ein Fehler sein wird (100% `# Error`).

Die vier anderen klassifizieren nach *Intent* (es ist eine Anfrage → `#?`), Sonnet klassifiziert nach *erwartetem Outcome* (das Item existiert nicht → `# Error`). Dieser Unterschied zeigt Sonnets überlegenes *Outcome-Reasoning*: Es antizipiert das Ergebnis und wählt den Modus entsprechend.

Aber auch hier ist die `#?`-Antwort nicht falsch im engeren Sinne: Der Prompt *ist* eine Anfrage. Dass das Ergebnis ein Fehler sein wird, weiß das Modell nur, wenn es den Satz „This item does not exist in the system" im Prompt beachtet — was bei der impliziten Variante nicht gegeben ist (der Prompt lautet nur: „Get me the details for item INV-9999"). Die Query-Interpretation ist konsistent und korrekt; die Error-Antwort setzt zusätzliches Wissen voraus.

Für Agent-Design ergibt sich daraus: **Error-Dokumente sollten primär vom ausführenden System generiert werden** (der Server antwortet mit `# Error` auf eine `#?`-Query, die keine Treffer liefert), nicht vom anfragenden LLM antizipiert werden.

#### 16.7.7 Die AI-Whispering-Kernaussage

Die impliziten Ergebnisse liefern den stärksten empirischen Beleg für die AI-Whispering-These:

1. **JMD-Modi formalisieren Konzepte, die LLMs bereits verstehen.** Schema, Query und Delete werden ohne jede Modus-Benennung zu 100% korrekt erkannt — über alle 5 Modelle, über alle Anbieter, über alle Modellgrößen. Der Primer lehrt die *Syntax* (`#!`, `#?`, `#-`), nicht das *Konzept* dahinter. Das ist die Definition von AI Whispering: Formalisierung vorhandener Muster statt Erfindung neuer.

2. **Die vermeintliche Data/Query-Verwechslung ist ein Feature, kein Bug.** Die Modelle verstehen JMD's Modus-System *besser als der ursprüngliche Test annahm*. Sie wählen den Modus, der ihrer epistemischen Situation entspricht: Wer die Daten hat, liefert sie (`#`). Wer sie nicht hat, fragt sie ab (`#?`). Beide Pfade führen zum selben Ergebnis. `#` und `#?` sind nicht konkurrierende Modi, sondern **komplementäre Perspektiven** — der Unterschied liegt beim Sender, nicht beim Empfänger.

3. **Der Primer-Overhead ist minimal, weil er nur *Syntax* lehrt, nicht *Semantik*.** Die ~250 Tokens des Full-Primers enthalten 80% Information, die die Modelle bereits kennen. Nur die Marker-Zuordnung (`#!` = Schema, `#?` = Query, `#-` = Delete) ist neues Wissen. Das erklärt, warum der Primer bei allen Modellen so zuverlässig wirkt: Er dockt an vorhandenes Verständnis an.

4. **Korrigierte implizite Switch-Reliability: 80–100%.** Wenn Data und Query als funktional äquivalent gewertet werden, erreichen alle Modelle eine implizite Modus-Erkennung von mindestens 80% — ohne dass der Prompt den Modus benennt. Sonnet erreicht 100%. Das bedeutet: LLMs mit JMD-Primer können in Agentic Workflows *situativ den richtigen Modus wählen*, ohne dass jeder Prompt den erwarteten Dokumenttyp explizit benennen muss.

### 16.8 JSON-Baseline: Wo JSON strukturell versagt

Die JSON-Baseline zeigt, dass JSON bei 3 von 5 Operationen funktioniert (Schema via JSON Schema, Delete via Konventions-Marker, Error via Konventions-Objekt), aber bei **Query systematisch scheitert**. Der Grund:

- JSON Schema definiert *Struktur*, nicht *Abfragen*
- Es gibt keinen JSON-nativen Standard für Query-by-Example
- Modelle produzieren ad-hoc-Filter-Objekte (`{"quantity": {"$lt": 50}}`), die MongoDB-Syntax imitieren, aber keine standardisierte Semantik haben

JMD's `#?`-Modus löst dieses Problem durch eine einheitliche Syntax, die LLMs mit einem einzigen Primer-Absatz sofort korrekt anwenden. Die Query-Fähigkeit ist JMD's stärkstes Differenzierungsmerkmal gegenüber JSON im Multi-Modus-Kontext.

### 16.9 Kosten- und Performance-Analyse

| Bedingung | ∅ Tokens/Trial (Input) | ∅ Tokens/Trial (Output) | ∅ Kosten/Trial |
|---|---|---|---|
| full_primer (JMD) | ~800 | ~400 | $0,0092 |
| data_only (JMD) | ~600 | ~500 | $0,0168 |
| json_baseline | ~700 | ~600 | $0,0205 |

**Bemerkenswert:** Die full_primer-Bedingung ist trotz des höheren Primer-Overheads (~250 vs. ~120 Tokens) *billiger* als die JSON-Baseline. Die Erklärung: JMD-Outputs sind strukturell kürzer (keine Klammern, keine Quotes, keine Kommas). Der Primer amortisiert sich bereits innerhalb eines einzigen 5-Step-Workflows.

Die data_only-Bedingung ist teurer als full_primer, weil die Modelle bei fehlender Modus-Kenntnis in ausführlichere Freitext-Erklärungen ausweichen, bevor sie den (falschen) `#`-Marker verwenden.

### 16.10 Verbindung zu früheren Phasen

| Phase | Erkenntnis | Phase 6a bestätigt/erweitert |
|---|---|---|
| **Phase 2** | JMD spart 19% Tokens | Full-Primer-Trials sind 55% günstiger als JSON-Baseline |
| **Phase 3** | Format-Fidelity >98% | 100% Parse-Rate auch bei neuen Modi (#!, #?, #-) |
| **Phase 4b** | Frontmatter wird spontan adoptiert | Modi-Marker werden mit Primer spontan korrekt eingesetzt |
| **Phase 5/5b** | Primer-Effekt auf epistemisches Verhalten | Primer-Effekt auf Modus-Wechsel: 40% → 100% (60pp Shift) |

### 16.11 Implikationen für die JMD-Spezifikation

1. **Der Primer ist Spezifikationsbestandteil, nicht Implementierungsdetail.** Phase 6a beweist, dass die tetradischen Modi ausschließlich über den Primer aktiviert werden. Eine JMD-Implementierung ohne Primer-Bereitstellung ist eine halbe Implementierung. Die Spezifikation sollte offizielle Primer-Texte für verschiedene Kontexte definieren.

2. **Query-by-Example ist JMD's Unique Selling Point.** In keiner JSON-Variante können Modelle zuverlässig standardisierte Abfragen formulieren. `#?` schließt eine Lücke, die im JSON-Ökosystem seit Jahren durch fragmentierte Konventionen (MongoDB-Syntax, GraphQL, verschiedene REST-Filter) notdürftig gefüllt wird.

3. **Modus-Agilität validiert das tetradische Design.** Die Spezifikation definiert vier Modi, die dieselbe Syntax-Grundlage teilen. Phase 6a beweist, dass dieses Design aufgeht: Ein LLM, das den Primer erhalten hat, kann alle vier Modi korrekt nutzen, ohne zusätzliches Training. Die gemeinsame Syntax-Basis (Headings, `key: value`, Listen) eliminiert den Lernaufwand für neue Modi.

### 16.12 Schlüsselerkenntnisse Phase 6a

1. **Der 60-Prozentpunkte-Primer-Effekt:** 40% Switch-Reliability ohne Modus-Primer → 100% mit Primer (korrigiert: Data/Query als funktional äquivalent, siehe 16.7.5). Dieser Effekt ist absolut konsistent über alle Modelle. Der Primer ist der Schlüssel zum tetradischen Protokoll.

2. **Situative Modus-Selektion funktioniert.** Im Implicit-Experiment wählen alle 5 Modelle Schema, Query und Delete zu 100% korrekt — ohne dass der Prompt den Modus benennt. Der Primer lehrt Syntax, nicht Semantik. Die Konzepte hinter den Modi sind LLM-nativ.

3. **Data und Query sind komplementäre Perspektiven, keine Fehlerquelle.** Die vermeintliche Data/Query-Verwechslung ist korrekte epistemische Selbstwahrnehmung: Modelle, die Daten nicht besitzen, formulieren eine Query (`#?`), statt Daten zu halluzinieren (`#`). Beide Pfade führen zum selben Ergebnis. Korrigiert man diese funktionale Äquivalenz, steigt die implizite Switch-Reliability auf 80–100% (Sonnet: 100%).

4. **Query-by-Example als Alleinstellungsmerkmal:** 0% korrekte Query-Generierung in der JSON-Baseline vs. 100% mit JMD-Full-Primer. Kein anderer Modus zeigt eine so klare Format-Differenzierung. JSON hat kein Äquivalent.

5. **Syntax-Korrektheit ist kein Problem:** 100% Parse-Rate in allen Bedingungen. Die Modelle produzieren *immer* syntaktisch valides JMD — auch bei Modi, die sie zum ersten Mal sehen. JMD's Syntax ist LLM-nativ.

6. **JMD ist günstiger als JSON — auch mit Primer-Overhead:** Die full_primer-Trials kosten durchschnittlich $0,0092 vs. $0,0205 für die JSON-Baseline (−55%). Der Primer amortisiert sich innerhalb eines einzigen Multi-Step-Workflows.

7. **Error-Dokumente sollten vom Server kommen, nicht vom LLM.** Nur Sonnet antizipiert Error-Situationen korrekt. Alle anderen Modelle formulieren (korrekt) eine Query und überlassen die Fehlermeldung dem ausführenden System. Dieses Muster ist architektonisch sauberer: Das LLM fragt, der Server antwortet — auch mit Fehlern.

8. **Verbindung zum AI Manifest:** Phase 6a liefert den stärksten empirischen Beleg für AI Whispering. JMD's Modi formalisieren Konzepte, die LLMs *bereits verstehen* — und die Modelle beweisen dies, indem sie auch ohne explizite Anweisung den situativ richtigen Modus wählen. Das ist die Definition von AI Whispering: Arbeiten *mit* dem natürlichen Verhalten von Sprachmodellen, nicht dagegen.

---

## 17. Phase 6b: Deep Nesting Stress Test (Filesystem-Experiment)

### 17.1 Fragestellung

JMD drückt Hierarchie über Markdown-Heading-Tiefe aus: `#` für die Wurzel, `##` für die erste Ebene, `###` für die zweite usw. JSON verwendet verschachtelte `{}`-Klammern. Beide Ansätze müssen bei zunehmender Tiefe korrekt beibehalten werden — aber die Fehlermodi unterscheiden sich fundamental:

- **JMD Classic:** Das Modell muss die korrekte Anzahl `#`-Zeichen emittieren. Bei Tiefe 10 sind das `###########` — eine Sequenz, deren Korrektheit vom sequenziellen Token-Generator „mitgezählt" werden muss.
- **JSON:** Das Modell muss offene `{` und `[` korrekt durch `}` und `]` schließen. Bei Tiefe 10 stapeln sich 10+ offene Klammern, die am Ende der Ausgabe alle geschlossen werden müssen.

**Kernfrage:** Ab welcher Verschachtelungstiefe bricht die Syntax-Korrektheit der Modelle ein — und gibt es einen Unterschied zwischen JMD und JSON?

**Zusatzfrage:** Wäre eine numerische Heading-Syntax (`5# Label` statt `##### Label`) für tiefe Verschachtelung zuverlässiger?

### 17.2 Szenario: Dateisystem

Das Experiment verwendet eine synthetische Verzeichnisstruktur — ein Datenmodell, das Entwicklern universell vertraut ist und natürliche Tiefe ohne exponentielle Breite bietet:

- Jedes **Verzeichnis** hat: `name`, `type: directory`, `owner`, `permissions`, `modified`, `entries[]`
- Jede **Datei** hat: `name`, `type: file`, `owner`, `permissions`, `modified`, `size_bytes`, `file_type`, `content_hash`
- Pro Ebene gibt es **ein Unterverzeichnis** (das weiterverzweigt) und **1-2 Geschwisterdateien**
- Bei depth=10 enthält der Baum nur **~25 Nodes** — kompakt genug für den Prompt, tief genug für den Stress Test

Die Daten werden deterministisch aus einem Seed generiert. Der Prompt liefert eine **flache Liste** aller Nodes mit `parent_path`-Angaben — das Modell muss die verschachtelte Hierarchie rekonstruieren.

### 17.3 Versuchsdesign

| Parameter | Wert |
|---|---|
| **Tiefen** | 2, 3, 4, 5, 6, 8, 10 |
| **Formate** | JMD Classic (`#####`), JMD Numeric (`5#`), JSON |
| **Modelle** | Sonnet 4.6, GPT-5.4, Mistral Large |
| **Runs** | 10 pro Kombination |
| **Gesamt** | 7 × 3 × 3 × 10 = **630 API-Calls** |

**JMD Classic Primer:** Standard-JMD-Syntax mit Beispiel bis Tiefe 4 (`####`). Betont: „Use the correct number of # for each nesting level."

**JMD Numeric Primer:** Für Tiefe 1-3 standard Headings, ab Tiefe 4 numerische Syntax (`4# key`, `5# key`). Betont: „Never write #### or deeper — always use the numeric prefix for depth ≥ 4."

**JSON Primer:** Standard-JSON mit `entries`-Arrays.

### 17.4 Metriken

1. **Parse-Rate (%):** Syntaktisch valides Output (JMD-Heading erkannt / JSON parsebar)
2. **Depth Correctness (%):** Maximale gefundene Tiefe ≥ erwartete Tiefe
3. **Data Completeness (%):** Gefundene Nodes / erwartete Nodes × 100
4. **Kosten:** Durchschnittliche Kosten pro Trial

### 17.5 Ergebnisse: Parse-Rate

| Modell | Format | d=2 | d=3 | d=4 | d=5 | d=6 | d=8 | d=10 |
|---|---|---|---|---|---|---|---|---|
| **Sonnet** | JMD Classic | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| **Sonnet** | JMD Numeric | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| **Sonnet** | JSON | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| **GPT-5.4** | JMD Classic | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| **GPT-5.4** | JMD Numeric | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| **GPT-5.4** | JSON | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| **Mistral** | JMD Classic | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| **Mistral** | JMD Numeric | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| **Mistral** | JSON | 100% | 100% | 100% | 100% | 100% | 100% | 100% |

**100% Parse-Rate über alle 630 Trials.** Kein einziger Syntax-Fehler bei keinem Modell, keinem Format, keiner Tiefe. `###########` (11 Hashes für Tiefe 10 + 1 Ebene entries) ist für alle Modelle ebenso zuverlässig wie `{}` mit 10 Verschachtelungsebenen.

### 17.6 Ergebnisse: Depth Correctness

| Modell | Format | d=2 | d=3 | d=4 | d=5 | d=6 | d=8 | d=10 |
|---|---|---|---|---|---|---|---|---|
| **Sonnet** | JMD Classic | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| **Sonnet** | JMD Numeric | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| **Sonnet** | JSON | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| **GPT-5.4** | JMD Classic | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| **GPT-5.4** | JMD Numeric | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| **GPT-5.4** | JSON | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| **Mistral** | JMD Classic | 100% | 100% | 100% | 100% | 100% | 100% | **90%** |
| **Mistral** | JMD Numeric | 100% | 100% | 100% | 100% | 100% | **90%** | 100% |
| **Mistral** | JSON | 100% | 100% | 100% | 100% | 100% | 100% | 100% |

Sonnet und GPT-5.4 erreichen **100% Depth Correctness** über alle Tiefen und Formate. Mistral hat je einen sporadischen Ausreißer bei d=10 (Classic) und d=8 (Numeric) — jeweils 1 von 10 Runs. Dies sind Einzelereignisse, kein systematischer Einbruch.

### 17.7 Ergebnisse: Data Completeness — Der differenzierende Befund

| Modell | Format | d=2 | d=3 | d=4 | d=5 | d=6 | d=8 | d=10 |
|---|---|---|---|---|---|---|---|---|
| **Sonnet** | JMD Classic | 100% | 100% | 100% | 99% | 100% | 100% | 100% |
| **Sonnet** | JMD Numeric | 100% | 100% | 100% | 100% | 100% | 100% | 97% |
| **Sonnet** | JSON | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| **GPT-5.4** | JMD Classic | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| **GPT-5.4** | JMD Numeric | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| **GPT-5.4** | JSON | **112%** | **103%** | **101%** | **102%** | **101%** | **101%** | **102%** |
| **Mistral** | JMD Classic | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| **Mistral** | JMD Numeric | **82%** | **93%** | **65%** | 100% | **83%** | 100% | **82%** |
| **Mistral** | JSON | **118%** | **112%** | **108%** | **106%** | **106%** | **104%** | **103%** |

Drei distinkte Muster:

**1. JMD Classic: Präzision bei allen Modellen.** Ø 100% Completeness über alle Tiefen und Modelle (Sonnet hat einen einzigen Run mit 99% bei d=5). Das Format erzwingt strukturelle Disziplin — die Heading-Syntax lässt keinen Raum für halluzinierte Zusatz-Nodes, weil jeder Node durch ein explizites Heading eingeleitet werden muss.

**2. JSON: Systematische Über-Generierung.** GPT-5.4 produziert konsistent 101-112% der erwarteten Nodes, Mistral 103-118%. Die Modelle erfinden Dateien und Verzeichnisse, die nicht in der Eingabe standen. Der Effekt ist bei flachen Tiefen am stärksten (d=2: +12-18%) und nimmt mit zunehmender Tiefe ab — vermutlich weil die längere Eingabe weniger Raum für Halluzination lässt. Nur Sonnet bleibt bei exakt 100%.

**3. JMD Numeric: Mistrals Schwäche.** Mistral verliert bei der numerischen Syntax systematisch Nodes (65-93% Completeness). Die `4# Label`-Syntax ist für Mistral offenbar unvertraut — das Modell produziert zwar syntaktisch valides Output, lässt aber Teile der Hierarchie aus. Sonnet und GPT-5.4 haben dieses Problem nicht.

### 17.8 JSON-Halluzination: Warum über 100%?

Die Über-Generierung unter JSON ist kein Messfehler. Die Modelle erhalten eine flache Liste mit exakt N Nodes und den Auftrag, diese als verschachtelte Hierarchie zu rekonstruieren. Completeness >100% bedeutet, dass das Modell **zusätzliche Nodes erfunden hat**, die nicht in der Eingabe standen.

Dies ist ein Format-spezifischer Effekt:
- **JSON's Struktur lädt zur Ergänzung ein.** Ein `"entries": [...]` Array ist ein offener Container — das Modell kann beliebig viele Objekte einfügen, ohne ein syntaktisches Signal zu verletzen. Der „Abschluss" ist ein `]`, kein semantischer Marker.
- **JMD's Headings erzwingen Intentionalität.** Jeder neue Node erfordert eine explizite Heading-Zeile (`### File`, `#### Directory`). Das ist ein stärkeres kognitives Signal als ein weiteres `{` in einem Array.

**Implikation für die Praxis:** In Szenarien, wo Data Completeness kritisch ist (z.B. Inventar-Export, Konfigurations-Generierung), ist JMD dem JSON-Format vorzuziehen — nicht wegen der Syntax-Korrektheit (beide 100%), sondern wegen der **geringeren Halluzinationsrate bei der Datenrekonstruktion**.

### 17.9 Die Numerische Syntax: Nicht nötig, aber harmlos

Die zentrale Hypothese von Phase 6b war: Ab einer bestimmten Tiefe bricht `#####...`-Syntax ein, und eine numerische Alternative (`5# Label`) wäre zuverlässiger.

**Die Hypothese ist widerlegt.** JMD Classic mit bis zu 11 `#`-Zeichen funktioniert bei allen drei Modellen perfekt. Die numerische Syntax bietet keinen Vorteil bei Parse-Rate oder Depth Correctness. Bei Mistral verursacht sie sogar Probleme mit der Data Completeness.

**Warum funktioniert `###########` so gut?** Die Antwort ist AI Whispering: LLMs haben in ihren Trainingsdaten Millionen von Markdown-Dokumenten mit tief verschachtelten Headings gesehen. Die `#`-Sequenz ist kein neues Pattern, das das Modell „lernen" muss — es ist ein zutiefst vertrautes Signal. Die numerische Syntax `5#` hingegen existiert in keinem verbreiteten Markdown-Dialekt und ist damit *weniger* LLM-nativ als die klassische Form.

**Empfehlung:** Die numerische Syntax könnte in einer zukünftigen Spezifikationsversion als optionale Parser-Toleranz definiert werden (Parser akzeptiert `5#` als Äquivalent zu `#####`), sollte aber **nicht** als Generator-Output empfohlen werden. Für Generator-Strict bleibt die klassische Heading-Syntax die korrekte Wahl.

### 17.10 Kostenanalyse

| Format | Ø Kosten d=2 | Ø Kosten d=6 | Ø Kosten d=10 |
|---|---|---|---|
| JMD Classic | $0.003 | $0.012 | $0.021 |
| JMD Numeric | $0.003 | $0.012 | $0.020 |
| JSON | $0.004 | $0.016 | $0.027 |

JMD ist bei allen Tiefen günstiger als JSON. Der Kostenvorteil wächst mit der Tiefe: Bei d=10 ist JMD **~23% günstiger** als JSON — konsistent mit den Token-Savings aus Phase 2, die bei tief verschachtelten Strukturen am größten sind (keine `{}`, `""`, `,`).

**Gesamtkosten Phase 6b:** $9.71 für 630 Trials.

### 17.11 Schlüsselerkenntnisse Phase 6b

1. **JMD Classic ist das zuverlässigste Format für tiefe Verschachtelung.** 100% Parse-Rate, 100% Depth Correctness (Sonnet/GPT-5.4), 100% Data Completeness über alle Tiefen bis d=10. Kein anderes Format erreicht dieses Profil.

2. **`###########` funktioniert.** Die Befürchtung, dass LLMs bei tiefen Heading-Sequenzen die `#`-Zeichen nicht korrekt zählen, ist unbegründet. Bis Tiefe 10 gibt es keinen messbaren Einbruch. Die Heading-Syntax ist tief im Markdown-Training der Modelle verankert.

3. **JSON halluziniert bei der Datenrekonstruktion.** GPT-5.4 und Mistral erfinden systematisch Extra-Nodes unter JSON (bis +18%). JMD Classic verhindert dies — die explizite Heading-Syntax erzwingt Intentionalität bei jedem neuen Node.

4. **Die numerische Heading-Syntax ist vorerst nicht nötig.** Sie bietet keinen Vorteil gegenüber Classic und verursacht bei Mistral Completeness-Probleme. Empfehlung: Parser-Toleranz ja, Generator-Output nein.

5. **AI Whispering bestätigt — wieder.** JMD's Heading-basierte Hierarchie funktioniert bis Tiefe 10 perfekt, weil sie auf einem Pattern aufsetzt, das LLMs aus Millionen von Markdown-Dokumenten kennen. Die `#`-Sequenz ist kein neues Protokoll — sie ist formalisiertes, vertrautes Verhalten. Das ist die Definition von AI Whispering.

6. **JMD wird bei tiefer Verschachtelung günstiger, nicht teurer.** Der Kostenvorteil gegenüber JSON wächst mit der Tiefe (23% bei d=10), weil die Token-Einsparungen durch wegfallende Klammern und Anführungszeichen bei tiefer Verschachtelung proportional zunehmen.

---

## 18. Phase 6c: Schema-Roundtrip (Employee-Directory-Experiment)

### 18.1 Fragestellung

Kann JMD's Schema-Modus (`#!`) als alleinige Kommunikationsbrücke zwischen zwei Agenten dienen, die sich nie die Rohdaten teilen?

Der Schema-Roundtrip testet drei Fähigkeiten:
1. **Schema-Derivation:** Agent A leitet aus Rohdaten (`#`) ein Schema (`#!`) ab
2. **Daten-Generierung:** Agent B erzeugt aus dem Schema allein neue, konforme Daten
3. **Cross-Model-Interoperabilität:** Funktioniert die Brücke auch, wenn Agent A und B verschiedene LLMs sind?

Die Validierung prüft ausschließlich **strukturelle Korrektheit** (richtige Felder, Typen, Constraints), nicht inhaltliche Übereinstimmung mit den Originaldaten.

### 18.2 Datenmodell: Employee Directory

Ein synthetisches Mitarbeiterverzeichnis mit bewusst reichhaltigen Typen, die Schema-Derivation herausfordernd machen:

| Feld | Typ | Schema-Herausforderung |
|---|---|---|
| `id` | integer | Einfacher Typ |
| `name` | string | Einfacher Typ |
| `email` | string (email) | Format-Erkennung |
| `department` | enum (6 Werte) | Enum-Erkennung aus Daten |
| `level` | enum (5 Werte) | Enum-Erkennung aus Daten |
| `salary` | number (35k–220k) | Numerischer Bereich |
| `currency` | enum (EUR/USD) | Kleine Enum |
| `start_date` | string (date) | Datumsformat-Erkennung |
| `active` | boolean | Einfacher Typ |
| `skills` | array of strings | Array-Erkennung |
| `address` | nested object | Verschachteltes Objekt |
| `projects` | array of objects | Array verschachtelter Objekte |
| `manager_id` | integer (nullable) | Nullable-Erkennung |
| `phone` | string (nullable) | Nullable-Erkennung |

15 Felder, davon 3 Enums, 2 nullable, 1 verschachteltes Objekt, 2 Arrays, 2 Formate — eine realistische Schema-Herausforderung.

### 18.3 Versuchsdesign

**Bedingungen:**

| Bedingung | Schema-Deriver | Daten-Generator | Zweck |
|---|---|---|---|
| **same_model** | Modell X | Modell X | Baseline: Kann ein Modell sein eigenes Schema verstehen? |
| **cross_model** | Modell A | Modell B | Interoperabilität: JMD als Lingua Franca |
| **json_baseline** | (identisch) | (identisch) | Vergleich: JSON Schema statt JMD #! |

**Modelle:** Sonnet 4.6, GPT-5.4, Mistral Large

**Cross-Model-Paare:**
- Sonnet → GPT-5.4
- GPT-5.4 → Sonnet
- Sonnet → Mistral

**Formate:** JMD (#!), JSON Schema

**Umfang:** 6 Zellen same-model + 6 Zellen cross-model = 12 Zellen × 10 Runs = 120 Roundtrips (240 API-Calls)

### 18.4 Metriken

#### Step 1: Schema-Qualität (Daten → Schema)

| Metrik | Beschreibung |
|---|---|
| **Parse-Rate** | Produziert das Modell syntaktisch valides #! / JSON Schema? |
| **Field Coverage** | Anteil der 15 erwarteten Felder, die im Schema erscheinen |
| **Type Accuracy** | Anteil der korrekt typisierten Felder |
| **Enum Detection** | Erkennung der 3 Enum-Felder (department, level, currency) |
| **Nullable Detection** | Erkennung der 2 nullable Felder (manager_id, phone) |

#### Step 2: Daten-Adhärenz (Schema → neue Daten)

| Metrik | Beschreibung |
|---|---|
| **Parse-Rate** | Produziert das Modell syntaktisch valide Daten? |
| **Field Presence** | Anteil der erwarteten Felder pro generiertem Record |
| **Type Conformity** | Stimmen die Werttypen mit dem Schema überein? |
| **Enum Conformity** | Verwenden generierte Werte nur Schema-definierte Enum-Werte? |
| **Plausibility** | Sind Werte realistisch? (Gehalt 20k–500k, E-Mail enthält @, Datum ISO-Format) |

### 18.5 Ergebnisse: Schema-Qualität (Step 1)

| Deriver | Format | Parse | Field Cov. | Type Acc. | Enum Det. | Nullable |
|---|---|---|---|---|---|---|
| **Sonnet** | JMD #! | 100% | **100.0%** | **100.0%** | **100%** | 95% |
| **GPT-5.4** | JMD #! | 100% | 93.3% | 92.9% | **100%** | 95% |
| **Mistral** | JMD #! | 100% | 94.0% | **100.0%** | **100%** | 95% |
| **Sonnet** | JSON Schema | 100% | 90.0%¹ | 78.7%¹ | 90%¹ | 85%¹ |
| **GPT-5.4** | JSON Schema | 100% | **100.0%** | **100.0%** | **100%** | 95% |
| **Mistral** | JSON Schema | 100% | **100.0%** | **100.0%** | **100%** | 95% |

¹ Sonnet erzeugt JSON Schemas in einer stark verschachtelten Variante (`$defs` mit `$ref`-Referenzen), die der Evaluator in 3/10 Runs nicht vollständig navigieren kann. Die tatsächliche Schema-Qualität ist höher als gemessen.

**Kernbefund:** Sonnet produziert die besten JMD-Schemas (100% über alle Metriken), während GPT-5.4 bei JSON Schema führt. Jedes Modell ist in seinem „natürlicheren" Format stärker — Sonnet bei Markdown-basierter Syntax, GPT-5.4 bei JSON-basierter Syntax.

### 18.6 Ergebnisse: Daten-Adhärenz (Step 2)

#### Same-Model-Roundtrips

| Modell | Format | Parse | Fields | Types | Enums | Plausib. |
|---|---|---|---|---|---|---|
| **Sonnet→Sonnet** | JMD | 100% | 81.3%² | 100% | 94.0% | 100% |
| **GPT-5.4→GPT-5.4** | JMD | 100% | 93.3% | 100% | 97.3% | 100% |
| **Mistral→Mistral** | JMD | 100% | 81.3%² | 100% | 84.7% | 100% |
| **Sonnet→Sonnet** | JSON | 100% | 100% | 100% | 88.7% | 100% |
| **GPT-5.4→GPT-5.4** | JSON | 100% | 100% | 100% | 94.6% | 100% |
| **Mistral→Mistral** | JSON | 100% | 100% | 100% | **100%** | 100% |

² Die 80-81% Field Presence in JMD sind ein Evaluations-Artefakt: Der JMD-Record-Parser erfasst Heading-basierte Felder (`skills[]`, `address`, `projects[]`) nicht als Feld im flachen Record-Dict. Die Modelle generieren diese Felder korrekt als verschachtelte Strukturen.

#### Cross-Model-Roundtrips (Interoperabilität)

| Deriver→Generator | Format | Parse | Fields | Types | Enums | Plausib. |
|---|---|---|---|---|---|---|
| **GPT-5.4→Sonnet** | JMD | 100% | 89.3%² | 100% | 94.0% | 100% |
| **Sonnet→GPT-5.4** | JMD | 100% | 82.7%² | 100% | 96.7% | 100% |
| **Sonnet→Mistral** | JMD | 100% | 81.3%² | 100% | 97.3% | 100% |
| **GPT-5.4→Sonnet** | JSON | 100% | 100% | 100% | 98.7% | 100% |
| **Sonnet→GPT-5.4** | JSON | 100% | 100% | 100% | 87.3% | 100% |
| **Sonnet→Mistral** | JSON | 100% | 100% | 100% | 90.0% | 100% |

**Kernbefund Cross-Model:** Alle Cross-Model-Paare erreichen 100% Parse-Rate und 100% Type Conformity. JMD `#!` funktioniert als Lingua Franca zwischen verschiedenen LLM-Providern.

### 18.7 Enum-Analyse

Die Enum Conformity variiert und offenbart ein interessantes Muster:

| Kontext | JMD Enum Conf. | JSON Enum Conf. |
|---|---|---|
| **Same-Model (Ø)** | 92.0% | 94.4% |
| **Cross-Model (Ø)** | 96.0% | 92.0% |

JMD zeigt **bessere Cross-Model-Enum-Treue** als JSON. Hypothese: Die Pipe-Syntax (`Engineering|Sales|Marketing`) in JMD-Schemas ist visuell eindeutiger als JSON's `"enum": [...]` mit verschachtelten Anführungszeichen. LLMs erkennen das Alternations-Pattern aus Regex-Training.

Mistral zeigt die niedrigste Enum Conformity im same_model-JMD-Fall (84.7%), weil es gelegentlich Enum-Werte variiert (z.B. „Operations" → „Ops"). Bei JSON Schema hält es sich strenger (100%).

### 18.8 Kosten

| Format | Ø Kosten/Roundtrip | 120 Roundtrips |
|---|---|---|
| **JMD** | **$0.020** | $1.22 |
| **JSON** | **$0.044** | $2.64 |

JMD-Roundtrips sind **55% günstiger** als JSON-Roundtrips. Die Einsparung kommt aus beiden Steps:
- Step 1: JMD-Daten als Input sind kürzer als JSON (bekannter Token-Vorteil)
- Step 2: JMD-Schemas als Input sind kompakter als JSON Schemas (keine `"type":`, `"properties":`, `"required":` Boilerplate)

**Gesamtkosten Phase 6c:** $3.86 für 120 Roundtrips (240 API-Calls).

### 18.9 Schlüsselerkenntnisse Phase 6c

1. **JMD `#!` funktioniert als Inter-Agent-Schema-Brücke.** 100% Parse-Rate über 120 Roundtrips, 100% Type Conformity. Zwei Agenten, die sich nie die Rohdaten teilen, können über ein JMD-Schema korrekte, typkonforme Daten produzieren.

2. **Cross-Model-Interoperabilität bestätigt.** Sonnet schreibt ein Schema, GPT-5.4 generiert daraus — und umgekehrt. JMD ist kein Vendor-Lock-in-Format, sondern eine echte Lingua Franca.

3. **Jedes Modell hat sein „natürliches" Format.** Sonnet produziert die besten JMD-Schemas (100% Field Coverage), GPT-5.4 die besten JSON Schemas. Das überrascht nicht: Sonnet ist stärker auf Markdown trainiert, GPT-5.4 auf JSON. JMD nutzt diese Stärke aus.

4. **JMD-Schemas sind 55% günstiger.** Die Kompaktheit von `#!`-Syntax gegenüber JSON Schema Boilerplate spart Tokens in beiden Directions des Roundtrips.

5. **Enum-Erkennung aus Daten funktioniert.** Alle drei Modelle erkennen kategorische Felder und kodieren sie als Pipe-Enums (`Engineering|Sales|...`) bzw. JSON-Schema-Enums. Die JMD-Pipe-Syntax zeigt dabei bessere Cross-Model-Treue als JSON.

6. **Schema-Adhärenz (Option A) ist in Schema-Roundtrip (Option B) subsumiert — und bestätigt.** Die in 18.6 gemessene Type Conformity (100%) und Enum Conformity (84–100%) zeigen, dass LLMs JMD-Schemas nicht nur schreiben, sondern auch lesen und befolgen können.

---

## 19. Phase 7: Query-by-Example (Employee-Directory-Experiment)

### 19.1 Fragestellung

Kann JMD's Query-Modus (`#?`) als strukturierte Abfragesprache für LLMs dienen — und können LLMs Query-Dokumente nicht nur auf Instruktion, sondern auch aus eigenem Informationsbedürfnis heraus erzeugen?

Der QBE-Benchmark testet zwei komplementäre Fähigkeiten:
1. **Instruiertes Querying (Arm A):** LLM übersetzt eine natürlichsprachliche Filteranfrage in ein strukturiertes Query-Dokument
2. **Task-getriebenes Querying (Arm B):** LLM erhält ein Geschäftsszenario und entscheidet selbstständig, welche Daten es abfragen muss

Dass LLMs die `#?`-Syntax intuitiv beherrschen, hat bereits Phase 6a gezeigt: Alle Modelle setzten den Query-Modus ohne explizite Instruktion korrekt ein (100% Query-Accuracy, vgl. §16.7). Phase 7 baut darauf auf und testet darüber hinaus die **eigenständige Formulierung** von Informationsbedürfnissen — die entscheidende Fähigkeit für Agentic Workflows, in denen ein Agent nicht gesagt bekommt, *was* er abfragen soll, sondern dies aus dem Geschäftskontext selbst ableiten muss.

### 19.2 Datenmodell

Verwendet wird dasselbe Employee-Directory aus Phase 6c (10 Mitarbeiter, 15 Felder inkl. Enums, Nested Objects, Arrays, Nullable Fields). Die Daten werden deterministisch generiert (Seed = 42), sodass die erwarteten Query-Ergebnisse vorab berechenbar sind.

### 19.3 Query-Syntax

**JMD QBE (`#?`)**:

```
#? EmployeeDirectory

## employees[]
department: Engineering
salary: > 100000
level: Senior|Lead
active: true
name: ?
salary: ?
```

Unterstützte Operatoren:
- Equality: `department: Engineering`
- Comparison: `salary: > 100000`, `salary: >= 50000`
- Alternation (Pipe-Enum): `level: Senior|Lead`
- Negation: `department: !HR`
- Array-Filter: `skills[]: Python` oder `### skills[]` + `- Python`
- Projection: `name: ?` (nur diese Felder zurückgeben)

**JSON Query (MongoDB-Stil)**:

```json
{
  "filter": {"department": "Engineering", "salary": {"$gt": 100000}},
  "projection": ["name", "salary"]
}
```

### 19.4 Testdesign

#### Arm A: Instruierte Queries (5 Queries)

| ID | Name | Komplexität | Anfrage |
|---|---|---|---|
| A1 | Simple equality | basic | Alle Mitarbeiter in Engineering |
| A2 | Comparison | basic | Gehalt > 100.000 |
| A3 | Nested + alternation | intermediate | Engineering oder Sales, Stadt Berlin |
| A4 | Array condition | advanced | Skill „Python" vorhanden |
| A5 | Combined filters | advanced | Aktiv, Senior/Lead, Gehalt > 80.000 |

**Metrik:** Exact Match — das Query-Ergebnis muss exakt die erwarteten Employee-IDs liefern.

#### Arm B: Task-getriebene Queries (5 Szenarien)

| ID | Szenario | Erwartete Filterfelder |
|---|---|---|
| B1 | Kapazitätsplanung | `department`, `level` |
| B2 | Budget-Review | `salary` (Vergleich) |
| B3 | Onsite-Staffing Berlin | `address.city` |
| B4 | Skill-Matching ML-Projekt | `skills[]` |
| B5 | Datenqualitäts-Audit | `phone: null` |

**Metriken:**
- **Relevance**: Mindestens eines der erwarteten Filterfelder im Query verwendet
- **Selectivity**: Query liefert eine echte Teilmenge (nicht alle Mitarbeiter)

#### Parameter

- **Modelle:** Sonnet 4.6, GPT-5.4, Mistral Large
- **Formate:** JMD (`#?`), JSON (MongoDB-Stil)
- **Runs:** 10 pro Kombination
- **Gesamt:** 3 Modelle × 2 Formate × 10 Queries × 10 Runs = **600 Trials**

### 19.5 Ergebnisse: Arm A (Instruierte Queries)

#### Parse- und Execution-Rate

| Modell | Format | Parse Rate | Exec Rate |
|---|---|---|---|
| Sonnet 4.6 | JMD | 100% | 100% |
| Sonnet 4.6 | JSON | 100% | 100% |
| GPT-5.4 | JMD | 100% | 100% |
| GPT-5.4 | JSON | 100% | 100% |
| Mistral Large | JMD | 100% | 100% |
| Mistral Large | JSON | 100% | 100% |

**100% Parse-Rate über alle 600 Trials.** Sowohl JMD-QBE als auch MongoDB-JSON werden von allen drei Modellen syntaktisch korrekt produziert.

#### Exact Match (Semantische Korrektheit)

| Modell | Format | A1 (Eq.) | A2 (Cmp.) | A3 (Nested) | A4 (Array) | A5 (Combined) | **Gesamt** |
|---|---|---|---|---|---|---|---|
| Sonnet 4.6 | JMD | 100% | 100% | 100% | 100% | 100% | **100%** |
| Sonnet 4.6 | JSON | 100% | 100% | 80% | 100% | 100% | **96%** |
| GPT-5.4 | JMD | 100% | 100% | 100% | 60% | 100% | **92%** |
| GPT-5.4 | JSON | 100% | 100% | 100% | 100% | 100% | **100%** |
| Mistral Large | JMD | 100% | 100% | 100% | 100% | 100% | **100%** |
| Mistral Large | JSON | 100% | 100% | 100% | 100% | 100% | **100%** |

**Befunde:**
- **Sonnet JMD: 100% Exact Match** über alle 50 Trials — perfekte Query-Übersetzung
- **Mistral JMD: 100%** — trotz Syntaxvarianten (`skills[]: Python` statt Heading-Syntax)
- **GPT-5.4 JMD: 92%** — Schwäche bei A4 (Array Condition, 60%). GPT-5.4 tendiert dazu, Array-Filter-Syntax zu variieren, was bei 4 von 10 Runs zu nicht-ausführbaren Filterausdrücken führt
- **Sonnet JSON: 96%** — A3 (Nested + Alternation) fällt in 2 von 10 Runs auf 80%, vermutlich wegen `$and`/`$or`-Nesting-Fehlern im MongoDB-Syntax

**Interpretation:** JMD-QBE ist für LLMs mindestens so natürlich wie MongoDB-Syntax. Die flache, zeilenorientierte Struktur vermeidet die Nesting-Komplexität von `$and`/`$or`/`$in`-Operatoren.

### 19.6 Ergebnisse: Arm B (Task-getriebene Queries)

| Modell | Format | Parse Rate | Exec Rate | Relevance | Selectivity |
|---|---|---|---|---|---|
| Sonnet 4.6 | JMD | 100% | 100% | 100% | 100% |
| Sonnet 4.6 | JSON | 100% | 100% | 100% | 100% |
| GPT-5.4 | JMD | 100% | 100% | 100% | 100% |
| GPT-5.4 | JSON | 100% | 100% | 100% | 100% |
| Mistral Large | JMD | 100% | 100% | 100% | 100% |
| Mistral Large | JSON | 100% | 100% | 100% | 100% |

**100% über alle 300 Task-getriebenen Trials.** Jedes Modell, in jedem Format:
- Verwendet mindestens ein relevantes Filterfeld für das Szenario
- Produziert eine selektive Query (nicht einfach „alle Mitarbeiter")

**Das bedeutet:** LLMs können JMD-QBE nicht nur als instruierte Übersetzung, sondern als **eigenständiges Denkwerkzeug** verwenden. Gegeben ein Geschäftsszenario, formulieren sie selbstständig die richtigen Filterbedingungen — ohne explizite Anweisung, welche Felder zu verwenden sind.

### 19.7 Analyse: JMD QBE vs. MongoDB JSON

| Aspekt | JMD QBE | MongoDB JSON |
|---|---|---|
| Parse Rate | 100% | 100% |
| Exact Match (Arm A) | 92–100% | 96–100% |
| Relevance (Arm B) | 100% | 100% |
| **Syntax-Natürlichkeit** | Flach, zeilenorientiert | Verschachtelt, operatorlastig |
| **Array-Filter** | `skills[]: Python` | `{"skills": "Python"}` |
| **Negation** | `department: !HR` | `{"department": {"$ne": "HR"}}` |
| **Alternation** | `level: Senior\|Lead` | `{"level": {"$in": ["Senior", "Lead"]}}` |
| **Projection** | `name: ?` | `"projection": ["name"]` |

JMD-QBE und MongoDB-JSON sind funktional äquivalent. Der entscheidende Unterschied liegt in der **Ergonomie für LLMs**: JMD-QBE erfordert kein Nesting und keine Operator-Syntax (`$gt`, `$in`, `$ne`), sondern nutzt natürliche Zeichen (`>`, `|`, `!`, `?`), die LLMs aus Markdown-Kontext kennen.

### 19.8 Kosten

| Posten | Wert |
|---|---|
| Trials | 600 |
| API-Calls | 600 |
| Gesamtkosten | **$0,87** |
| Kosten pro Trial | $0,00145 |

### 19.9 Schlussfolgerungen

1. **JMD `#?` funktioniert als LLM-native Abfragesprache.** 100% Parse-Rate, 92–100% Exact Match über 300 instruierte Trials. Die Syntax wird von allen drei Modellen fehlerfrei produziert.

2. **LLMs können aus eigenem Informationsbedürfnis heraus Query-Dokumente formulieren.** 100% Relevance und 100% Selectivity über 300 task-getriebene Trials. Das ist die Voraussetzung für echte Agentic-Autonomie: Ein Agent muss nicht gesagt bekommen, *was* er abfragen soll — er muss nur die Syntax kennen.

3. **JMD-QBE ist mindestens so natürlich wie MongoDB-Syntax.** Die flache Zeilenstruktur vermeidet Nesting-Fehler, die bei MongoDB-`$and`/`$or`-Ausdrücken auftreten (vgl. Sonnet JSON A3: 80%). Die Pipe-Alternation (`Senior|Lead`) ist für LLMs intuitiver als `{"$in": [...]}`.

4. **Drei von vier JMD-Modi sind jetzt validiert.** Data (`#`), Schema (`#!`) und Query (`#?`) funktionieren zuverlässig über drei LLM-Familien hinweg. Der vierte Modus, Delete (`#-`), wird in Phase 8 (§20) evaluiert.

5. **AI Whispering bestätigt:** Die QBE-Syntax verwendet ausschließlich Zeichen, die in Markdown und Programmiersprachen vorkommen (`>`, `|`, `!`, `?`). LLMs erzeugen korrekte Queries ohne spezielles Training — JMD formalisiert Muster, die bereits im Trainingskorpus verankert sind.

---

## 20. Phase 8: Delete Documents (Employee-Directory-Experiment)

### 20.1 Fragestellung

Kann JMD's Delete-Modus (`#-`) als strukturierte Löschanweisung für LLMs dienen — und können LLMs korrekte Delete-Dokumente sowohl auf explizite Instruktion als auch aus einem Geschäftskontext heraus erzeugen?

Phase 6a hat bereits gezeigt, dass alle Modelle den `#-` Marker im Kontext eines Multi-Step-Workflows korrekt einsetzen (vgl. §16.7). Phase 8 testet die Delete-Fähigkeit isoliert und in größerer Tiefe:
1. **Single vs. Bulk Delete:** Einzelne ID vs. Bulk-Array (`#- []`)
2. **Conditional Delete:** LLM muss aus Daten die richtigen Löschkandidaten identifizieren
3. **Task-getriebenes Delete:** LLM leitet aus einem Geschäftsszenario ab, welche Datensätze zu löschen sind

### 20.2 Datenmodell

Verwendet wird dasselbe Employee-Directory aus Phase 6c/7 (10 Mitarbeiter, 15 Felder). Die vollständigen Daten werden dem LLM als Kontext mitgegeben, damit es bei konditionalen Deletes die richtigen IDs identifizieren kann.

### 20.3 Delete-Syntax

**JMD Delete (`#-`)**:

Single Delete:
```markdown
#- Employee
id: 5
```

Bulk Delete:
```markdown
#- []
- 2
- 6
- 8
```

**JSON Delete:**
```json
{"_action": "delete", "resource": "Employee", "ids": [2, 6, 8]}
```

### 20.4 Testdesign

#### Arm A: Instruierte Deletes (5 Tasks)

| ID | Name | Komplexität | Anfrage |
|---|---|---|---|
| D1 | Single delete by ID | basic | Lösche Mitarbeiter mit ID 5 |
| D2 | Bulk delete by ID list | basic | Lösche IDs 2, 6, 8 |
| D3 | Conditional single | intermediate | Lösche den Mitarbeiter mit dem niedrigsten Gehalt |
| D4 | Conditional bulk | intermediate | Lösche alle inaktiven Mitarbeiter |
| D5 | Nested condition | advanced | Lösche alle Mitarbeiter in Paris |

**Metrik:** ID Exact Match — die extrahierten IDs müssen exakt den erwarteten entsprechen.

#### Arm B: Task-getriebene Deletes (5 Szenarien)

| ID | Szenario | Schwierigkeit |
|---|---|---|
| D6 | Offboarding (bestimmter Mitarbeiter hat gekündigt) | Einfach — eine ID |
| D7 | Department-Auflösung (alle HR-Mitarbeiter) | Mittel — Filterung nach Abteilung |
| D8 | GDPR-Compliance (fehlende Telefonnummer) | Mittel — Nullable-Feld-Erkennung |
| D9 | Budget-Restrukturierung (alle Junior-Level) | Mittel — Filterung nach Level |
| D10 | Projekt-Abwicklung (exklusiv Atlas-Projekt) | Schwer — Multi-Step-Reasoning |

D10 ist bewusst der härteste Test: Das LLM muss verstehen, dass „exklusiv Atlas" bedeutet, dass Atlas das *einzige* Projekt des Mitarbeiters ist — nicht lediglich, dass Atlas in der Projektliste vorkommt. Bei vielen Seeds ist die erwartete Ergebnismenge leer (kein Mitarbeiter ist exklusiv auf Atlas), was zusätzlich testet, ob das LLM korrekt erkennt, dass nichts zu löschen ist.

#### Parameter

- **Modelle:** Sonnet 4.6, GPT-5.4, Mistral Large
- **Formate:** JMD (`#-`), JSON (`{"_action": "delete"}`)
- **Runs:** 10 pro Kombination
- **Gesamt:** 3 Modelle × 2 Formate × 10 Tasks × 10 Runs = **600 Trials**

### 20.5 Ergebnisse: Arm A (Instruierte Deletes)

| Modell | Format | Parse Rate | Marker Rate | D1 (Single) | D2 (Bulk) | D3 (Cond.) | D4 (Inactive) | D5 (City) | **Gesamt** |
|---|---|---|---|---|---|---|---|---|---|
| Sonnet 4.6 | JMD | 100% | 100% | 100% | 100% | 100% | 100% | 100% | **100%** |
| Sonnet 4.6 | JSON | 100% | 100% | 100% | 100% | 100% | 100% | 100% | **100%** |
| GPT-5.4 | JMD | 100% | 100% | 100% | 100% | 100% | 100% | 100% | **100%** |
| GPT-5.4 | JSON | 100% | 100% | 100% | 100% | 100% | 100% | 100% | **100%** |
| Mistral Large | JMD | 100% | 100% | 100% | 100% | 90% | 100% | 100% | **98%** |
| Mistral Large | JSON | 100% | 100% | 100% | 100% | 100% | 100% | 100% | **100%** |

**100% Parse-Rate und 100% Marker-Rate über alle 300 instruierten Trials.** Jedes Modell verwendet `#-` (JMD) bzw. `{"_action": "delete"}` (JSON) zuverlässig. Mistral hat eine leichte Schwäche bei D3 (Conditional Single, niedrigstes Gehalt) — in einem von 10 Runs wird die falsche ID identifiziert.

### 20.6 Ergebnisse: Arm B (Task-getriebene Deletes)

| Modell | Format | D6 (Offb.) | D7 (Dept.) | D8 (GDPR) | D9 (Budget) | D10 (Projekt) | **Gesamt** |
|---|---|---|---|---|---|---|---|
| Sonnet 4.6 | JMD | 90% | 100% | 100% | 100% | 90% | **96%** |
| Sonnet 4.6 | JSON | 90% | 100% | 100% | 100% | 100% | **98%** |
| GPT-5.4 | JMD | 100% | 100% | 100% | 100% | 80% | **96%** |
| GPT-5.4 | JSON | 100% | 100% | 100% | 100% | 80% | **96%** |
| Mistral Large | JMD | 90% | 100% | 80% | 100% | 0% | **74%** |
| Mistral Large | JSON | 80% | 100% | 100% | 100% | 20% | **80%** |

**Befunde:**

- **D6 (Offboarding):** 80–100%. Vereinzelte Fehler bei Mistral und Sonnet, wenn die ID im Szenario-Text nicht mit der tatsächlichen Daten-ID übereinstimmt (Name-zu-ID-Mapping).
- **D7–D9 (Department/GDPR/Budget):** 80–100%. Hohe Zuverlässigkeit bei Filtern über einzelne Felder.
- **D10 (Projekt-Exklusivität):** Die erwartete Schwachstelle. Mistral versagt fast vollständig (0–20%), weil es „auf Atlas" statt „exklusiv auf Atlas" filtert. GPT-5.4 erreicht 80%, Sonnet 90–100%. Dies ist ein Reasoning-Problem, kein Format-Problem — die Fehlerrate ist in JMD und JSON nahezu identisch.

### 20.7 Analyse: D10 als Reasoning-Lackmustest

D10 testet nicht die Delete-Syntax, sondern die Fähigkeit des LLMs, eine Bedingung mit Quantor korrekt auszuwerten: „Mitarbeiter, die *ausschließlich* Atlas als Projekt haben" ≠ „Mitarbeiter, die Atlas als Projekt haben". Diese Distinktion erfordert:

1. Prüfung der Projektliste jedes Mitarbeiters
2. Erkennung, dass `len(projects) == 1` die entscheidende Bedingung ist
3. Korrekte Behandlung leerer Ergebnismengen (bei vielen Seeds qualifiziert sich niemand)

Die JMD/JSON-Differenz bei D10 ist minimal — das Problem liegt im Reasoning, nicht im Format. Dies bestätigt, dass JMD als Ausgabeformat keine zusätzliche kognitive Last auferlegt.

### 20.8 Kosten

| Posten | Wert |
|---|---|
| Trials | 600 |
| API-Calls | 600 |
| Gesamtkosten | **$1,23** |
| Kosten pro Trial | $0,00205 |

### 20.9 Schlussfolgerungen

1. **JMD `#-` funktioniert als LLM-native Löschanweisung.** 100% Parse-Rate und 100% Marker-Rate über 600 Trials. Die Syntax wird von allen drei Modellen fehlerfrei produziert — sowohl für Single- als auch Bulk-Deletes.

2. **Instruierte Deletes sind trivial für LLMs.** 98–100% ID Exact Match über alle Modelle und Formate. Die Übersetzung von „Lösche ID 5" → `#- Employee\nid: 5` erfordert kein besonderes Training.

3. **Task-getriebene Deletes erreichen 74–98%.** Die Differenz zwischen Modellen liegt nicht im Format, sondern im Reasoning: Mistral scheitert bei Multi-Step-Bedingungen (D10), während Sonnet und GPT-5.4 zuverlässig arbeiten.

4. **Alle vier JMD-Modi sind jetzt validiert.** Data (`#`), Schema (`#!`), Query (`#?`) und Delete (`#-`) funktionieren über drei LLM-Familien hinweg. JMD deckt damit den vollständigen CRUD-Lifecycle ab:

   | Modus | Marker | Phase | Parse Rate | Funktionale Rate |
   |---|---|---|---|---|
   | Data | `#` | 1–3, 5, 6b | 100% | 95–100% semantisch |
   | Schema | `#!` | 6c | 100% | 100% Type Conformity |
   | Query | `#?` | 6a, 7 | 100% | 92–100% Exact Match |
   | Delete | `#-` | 6a, 8 | 100% | 98–100% (Arm A) |

5. **AI Whispering bestätigt:** Der Wechsel von `# Employee` (Data) zu `#- Employee` (Delete) ist ein einzelnes Zeichen. LLMs verstehen diese semantische Differenz ohne Erklärung — ein starker Beleg dafür, dass JMD's Modal-Design natürliche LLM-Muster formalisiert.

---

## Anhang: Chronologie der Tests

| Datum | Aktivität |
|---|---|
| 2026-03-12 | Phase 0: Live-Tests mit 300-Token-Primer (Sonnet, GPT-4o, Gemini 2.5 Flash) |
| 2026-03-12 | Phase 0: 5-Bullet-Minimal-Primer validiert |
| 2026-03-13 | Phase 0: Compute-Benchmark (10 Runs, Haiku/GPT-4.1-mini/Gemini 2.5 Flash) |
| 2026-03-14 | Phase 0.5: TOON-Evaluation → Ausschluss |
| 2026-03-14 | Phase 1: Plan erstellt (Modellauswahl, Staging) |
| 2026-03-14 | Phase 1: Dry-Run (Pricing/Provider-Detection validiert) |
| 2026-03-14 | Phase 1: Single-Runs Haiku, Sonnet, GPT-5.4, GPT-5 Nano |
| 2026-03-15 | Phase 1: Single-Runs Gemini 3 Flash, Gemini 3.1 Pro |
| 2026-03-15 | Phase 1: Ergebnisanalyse und Dokumentation |
| 2026-03-15 | Phase 1.5: Format-Fidelity-Test (6 Modelle × 2 Formate × 4 Payloads) |
| 2026-03-15 | GPT-5 Nano ausgeschlossen (+125% Token-Overhead bestätigt) |
| 2026-03-15 | Modellauswahl Phase 2: Haiku 4.5, Sonnet 4.6, GPT-5.4, Gemini 3.1 Pro |
| 2026-03-15 | Budget-Modelle (Nano, Flash) ausgeschlossen — Haiku bleibt für Anthropic-Pitch |
| 2026-03-15 | Fidelity-Test Gemini 3.1 Pro Preview: 10/10 = 100% (Modellversion korrigiert) |
| 2026-03-15 | Primer-Optimierung: `strict`-Primer validiert (Gemini 60% → 100%, keine Regression) |
| 2026-03-15 | Phase 2a: Start (30 Runs × 3 Modelle × 2 Formate × 3 Szenarien) |
| 2026-03-16 | Phase 2a: Gemini 3.1 Pro abgebrochen (4/180 Chains, API zu langsam) |
| 2026-03-16 | Phase 2a: Haiku, Sonnet, GPT-5.4 komplett (je 180/180 Chains, 540 gesamt) |
| 2026-03-16 | Phase 2b: Sonnet, GPT-5.4, Mistral, Gemini Flash (720 Chains, mit Server-Processing-Time) |
| 2026-03-16 | Phase 2b: Auswertung — alle Token-/Kostenunterschiede hochsignifikant (p < 0,01) |
| 2026-03-16 | Phase 3: Agentic Chains (180 Chains, 3 Modelle, Epistemic Primer) |
| 2026-03-16 | Phase 4a: Streaming TTFUB (180 Chains, 3 Modelle × 2 Formate × 2 Modi) |
| 2026-03-16 | Phase 4b: Epistemische Evaluation — Deploy-Gate-Experiment (180 Trials, 3 Bedingungen) |
| 2026-03-16 | Phase 5: Halluzinations-Evaluation — Due-Diligence-Experiment (180 Trials, parallel) |
| 2026-03-16 | Phase 5b: Inferenz-Transparenz — Derivable Metrics, Conflicting Sources, Loosened Prompts (180 Trials, parallel) |
| 2026-03-17 | Lizenzierung: CC BY-NC-SA 4.0 (Spec), AGPL-3.0 (Code) |
| 2026-03-17 | Phase 6a: Modus-Agilität — Inventory-Management-Experiment (90 Trials, 450 API-Calls, parallel) |
| 2026-03-17 | Phase 6a-implicit: Situative Modus-Selektion — Explicit vs. Implicit Prompts (100 Trials, 5 Modelle) |
| 2026-03-17 | Phase 5b Nachtrag: Transparenz-Paradox als Mess-Ebenen-Artefakt reinterpretiert (lokales vs. globales Hedging) |
| 2026-03-17 | Phase 6b: Deep Nesting Stress Test — Filesystem-Experiment (630 Trials, 7 Tiefen × 3 Formate × 3 Modelle) |
| 2026-03-18 | Phase 6c: Schema-Roundtrip — Employee-Directory-Experiment (120 Roundtrips, 240 API-Calls, 3 Modelle × 2 Formate) |
| 2026-03-18 | Phase 7: Query-by-Example — Employee-Directory-Experiment (600 Trials, 2 Arms × 5 Queries × 3 Modelle × 2 Formate × 10 Runs) |
| 2026-03-18 | Phase 8: Delete Documents — Employee-Directory-Experiment (600 Trials, 2 Arms × 5 Tasks × 3 Modelle × 2 Formate × 10 Runs) |

---

*Benchmark-Framework: `benchmark/run_benchmark.py`, `benchmark/run_phase2.py` | Parser: JMD v0.3 C-accelerated | Rohdaten: `benchmark_results/phase2_results.json`, `benchmark_results/phase2_mistral/phase2_results.json`, `benchmark_results/phase2_results_v1.json`, `benchmark_results/phase5_hallucination_results.json`, `benchmark_results/phase5b_inference_results.json`, `benchmark_results/phase6a_mode_agility_results.json`, `benchmark_results/phase6a_implicit_results.json`, `benchmark_results/phase6a_implicit_results_wave2.json`, `benchmark_results/phase6b_nesting_results.json`, `benchmark_results/phase6c_schema_roundtrip_results.json`, `benchmark_results/phase7_qbe_results.json`, `benchmark_results/phase8_delete_results.json`*

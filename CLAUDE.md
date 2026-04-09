# Workspace: JMD Ecosystem

Dieser Workspace umfasst die JMD-Spezifikation, die Referenzimplementierung und mehrere MCP-Server. Alle Projekte folgen denselben Designprinzipien.

## AI Whispering als Designmethodik

AI Whispering ist die Leitpraxis dieses Workspaces: Beobachte, was Sprachmodelle natürlich tun, verstehe warum, und arbeite mit diesen Tendenzen statt gegen sie.

### Prinzipien fuer Designentscheidungen

1. **Observable Reality, Not Theory** — Jede Syntaxentscheidung, jedes Protokolldesign, jedes API-Format muss empirisch begruendet sein. "Wuerde ein LLM das von sich aus so produzieren?" ist der zentrale Test.

2. **Kontext statt Befehle** — Modelle scheitern weniger an fehlenden Anweisungen als an fehlendem Kontext. Systeme so gestalten, dass das Modell seine Situation versteht, statt es mit Regelwerken zu ueberfrachten.

3. **Reibung kostet Compute** — Wenn ein Format gegen natuerliche Modelltendenzen laeuft, entstehen Syntaxfehler, Retries, Validierungsfehler. Jeder davon verbraucht GPU-Zyklen. Nachhaltiges Design minimiert diese Reibung.

4. **Formalisieren statt Erfinden** — JMD erfindet keine neue Syntax, sondern formalisiert Markdown-Strukturen, die LLMs bereits zuverlaessig erzeugen: Headings fuer Hierarchie, Key-Value-Paare, Bullet-Listen, Leerzeilen als Abgrenzung.

5. **Generator-strict, Parser-tolerant** — Serializer erzeugen kanonische Syntax. Parser akzeptieren natuerliche Variationen, die LLMs produzieren.

6. **Streaming als Grundeigenschaft** — Kein Feature, das nachtraeglich ergaenzt wird, sondern intrinsische Konsequenz zeilenorientierter Syntax ohne schliessende Delimiter.

7. **Minimum Viable Instruction** — Modelle brauchen nur ~80 Tokens (5 Bullet Points), um valides JMD zu erzeugen. Jedes Design, das umfangreiche Anleitungen erfordert, ist ein Warnsignal.

### Anwendung auf MCP-Server

Bei der Arbeit an den MCP-Servern diese Prinzipien als Bewertungsmassstab nutzen:

- **Tool-Beschreibungen**: Knapp und kontextreich statt regelbasiert. Das Modell soll verstehen, *was* das Tool tut, nicht eine Checkliste abarbeiten.
- **Input/Output-Formate**: JMD bevorzugen, wo es den Datenaustausch effizienter macht. Kein Selbstzweck — JSON bleibt dort, wo es besser passt (z.B. bei reinen Maschine-zu-Maschine-Schnittstellen ohne LLM-Beteiligung).
- **Fehlerrueckmeldungen**: Kontextreich und strukturiert, sodass das Modell den Fehler einordnen und korrigieren kann, statt nur einen Fehlercode zu sehen.
- **Schema-Design**: Flache, uebersichtliche Strukturen bevorzugen. Tiefe Verschachtelung erhoet die Fehlerrate bei LLM-generierter Ausgabe.

## Code-Qualitaet

Workspace-weit verbindlich fuer alle Projekte:

- **Google Python Style Guide** als Coding-Standard.
- **Ruff** und **Mypy strict** muessen vor jedem Test-Lauf und jedem Commit fehlerfrei durchlaufen.
- Ruff-Regeln: E, W, F, I, N, D (Google convention), B, UP. Line-length 80.
- Docstrings: Google-Style (Args, Returns, Raises).
- Type-Hints: Durchgehend, keine Any-Escapes ohne Begruendung.

## Technischer Kontext

- **jmd-spec**: Spezifikation v0.3 (stabil), Begleitdokumente (ai-whispering, efficiency-analysis, jmd-over-xml)
- **jmd-impl**: Python-Referenzimplementierung (v0.4.1), optionale C-Beschleunigung, vollstaendige API
- **jmd-mcp-***: MCP-Server fuer verschiedene Backends (SQL, SmartSuite, Office, OAuth2, Mail, Keyring)

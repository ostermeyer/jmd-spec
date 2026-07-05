# IANA Media Type Registration: `application/jmd`

**Purpose of this document.** This is a provisional registration request
for the media type `application/jmd`, following the template defined in
RFC 6838 §5.6. It is prepared for submission to `media-types@iana.org`
under the Provisional Registration procedure (RFC 6838 §5.3).

**Upgrade path.** The provisional registration secures the name and is
useful in its own right. For permanence there are three honest options:
(1) pursue IETF adoption of the Internet-Draft (natural venues: HTTPAPI
or DISPATCH; `application/yaml` via RFC 9512 is the blueprint), which
supports a Standards-Tree entry; (2) remain provisional indefinitely —
permissible, but weaker for adoption arguments; (3) fall back to the
personal tree (`application/prs.jmd`) — avoided deliberately, as it
would break the name. Strategy and current status are tracked in
ROADMAP.md.

---

## Submission E-Mail Template

When ready to submit, send the body below to `media-types@iana.org`.
Suggested subject line: *"Request for registration: application/jmd (provisional)"*.

---

```
To: media-types@iana.org
Subject: Request for registration: application/jmd (provisional)

Dear IANA Media Types Reviewers,

I am requesting the provisional registration of the media type
"application/jmd" for JMD (JSON Markdown), a text-based structured data
format. The registration template follows below, per RFC 6838 §5.6.

Type name:
    application

Subtype name:
    jmd

Required parameters:
    None

Optional parameters:
    None

Encoding considerations:
    JMD is a text format and MUST be encoded as UTF-8 (RFC 3629).
    Documents consisting entirely of ASCII characters are 7-bit safe;
    documents containing non-ASCII UTF-8 byte sequences require 8-bit
    transport. Content-Transfer-Encoding values such as "base64" or
    "quoted-printable" are permitted for transport systems that require
    7-bit encoding (such as historical e-mail), but are neither
    necessary nor recommended for modern HTTP or MCP transport.

Security considerations:
    The normative treatment is Section 24 of the JMD Specification;
    this template summarizes it. JMD inherits the security posture of
    "application/json", with one format-specific addition (item 1).

    1.  Structure injection in naive generation. JMD assigns
        structural meaning to line starts (headings, mode markers,
        list items, frontmatter position). A generator MUST emit
        untrusted content as quoted strings (RFC 8259 escaping) and
        MUST NOT interpolate untrusted text into bare-value, key,
        label, or frontmatter position (Specification Section 24.1).
        A JMD byte sequence contains exactly one document
        (Specification Section 18.0); an injected root heading or
        mode marker mid-document therefore produces a parse error
        rather than a second, potentially destructive document.

    2.  Injection into downstream rendering contexts. JMD string
        content is literal data, but documents may contain characters
        that are structurally significant in downstream contexts
        (HTML, SQL, shell). Receivers that render JMD content into
        such contexts MUST apply the appropriate escaping. This is
        identical to the JSON situation and is not specific to JMD.

    3.  Parser resource consumption. A conforming JMD parser processes
        documents in O(n) time and O(d) stack depth, where n is the
        document length in bytes and d is the maximum heading depth.
        The grammar itself places no bound on depth, line length,
        blockquote length, or field count; implementations SHOULD
        enforce practical, configurable bounds (a reasonable default
        depth bound is 32) to prevent stack exhaustion and memory
        abuse from adversarial inputs. Rejecting a document that
        exceeds a resource bound is a resource-limit error, not a
        conformance violation (Specification Section 24.3).

    4.  Content confusion with Markdown. JMD and conventional Markdown
        share surface syntax, but JMD is not guaranteed to be valid
        CommonMark: heading depth beyond six and the mode markers
        "#!", "#?", "#-" are not ATX headings. A receiver that
        renders a JMD document as Markdown will produce misleading
        output. Implementations MUST dispatch on the declared
        Content-Type and not on file content sniffing.

    5.  No active content. JMD has no scripting, no template
        expansion, no external reference resolution, no schema
        validation directives, and no anchor/alias mechanism. Parsing
        a JMD document does not trigger network access, code
        execution, or arbitrary I/O. This is identical to the JSON
        security model.

    6.  Privacy. JMD documents are opaque structured data. They do not
        carry fragment identifiers, external references, or embedded
        URIs that are interpreted implicitly by a conforming parser.
        Any URI-valued fields are application-level data; no JMD
        parser is required to follow them.

    7.  Streaming parse semantics. JMD is line-oriented and every
        completed line is independently parseable, and each framing
        unit carries exactly one document (Specification Section
        18.0). A partial JMD document may be partially processed by a
        receiver before the full document has arrived. Implementations
        that act on streaming data before the document is complete
        MUST ensure that such actions are safe under truncation (for
        example, a database write that commits only when the framing
        unit terminates cleanly).

Interoperability considerations:
    JMD is defined such that every valid data document is in bijection
    with a JSON value: parsing JMD yields a JSON value; serializing a
    JSON value yields a JMD document; and the roundtrip
    JMD -> JSON -> JMD preserves the value up to canonical
    normalization (key ordering and number formatting variations
    permitted by RFC 8259).

    Multiple valid JMD representations may exist for the same JSON
    value. This is by design and matches JSON's own freedom in object
    key ordering. Interoperability between JMD implementations
    requires only that each agrees on the value, not on the byte
    sequence that represents it.

    JMD defines four document modes (data, query, schema, delete)
    distinguished by the root heading marker. Only data documents are
    in bijection with JSON values; query, schema, and delete documents
    carry application-interpreted expressions as string field values
    and are intended for use by consuming applications that understand
    those conventions.

    Line-ending handling (Specification Section 11.2): canonical form
    uses "\n" (LF). A conforming parser accepts "\r\n" by consuming the
    "\r" as part of the line terminator; a "\r" not followed by "\n" is
    a parse error. A single leading U+FEFF (byte order mark) is
    consumed and ignored; generators never emit one.

Published specification:
    JMD Specification v0.3.5, available at:
        https://github.com/ostermeyer/jmd-spec/blob/main/jmd-spec-v0_3.md

    A companion proposal for HTTP integration is available at:
        https://github.com/ostermeyer/jmd-spec/blob/main/jmd-over-http.md

    An Internet-Draft describing JMD is available in the IETF
    Datatracker:
        draft-ostermeyer-jmd-00
        https://datatracker.ietf.org/doc/draft-ostermeyer-jmd/
    This registration request should be treated as provisional until
    the Internet-Draft is published as an RFC, at which point the
    registration can be promoted under the Specification Required or
    Standards Action procedures.

Applications that use this media type:
    - MCP (Model Context Protocol) servers for LLM tool integration
    - REST APIs with LLM agent clients
    - Streaming data pipelines with line-level event processing
    - LLM-generated structured output in agentic workflows
    - Service-to-service data exchange as a JSON alternative
    - Configuration files for LLM-native tooling

Fragment identifier considerations:
    None defined by this specification. A future revision of the JMD
    specification may define fragment identifiers for addressing
    specific elements within a JMD document (field paths, heading
    identifiers, or similar).

Additional information:
    Deprecated alias names for this type:  None
    Magic number(s):                        None
    File extension(s):                      .jmd
    Macintosh file type code(s):            TEXT

Person & email address to contact for further information:
    Andreas Ostermeyer <andreas@ostermeyer.de>

Intended usage:
    COMMON

Restrictions on usage:
    None

Author:
    Andreas Ostermeyer <andreas@ostermeyer.de>

Change controller:
    Andreas Ostermeyer <andreas@ostermeyer.de>

    Upon publication of a Standards-Track Internet-Draft for JMD, the
    change controller will become the IETF.

Provisional registration?
    Yes

Thank you for your consideration.

Best regards,
Andreas Ostermeyer
andreas@ostermeyer.de
```

---

## Review Checklist Before Sending

- [ ] The "Published specification" URLs resolve and point to the
      expected files — in particular, the repository must be public and
      show v0.3.5 (push before sending).
- [ ] The contact e-mail is current.
- [x] Parameters: `charset` and `version` removed (2026-07-03),
      following the precedent of RFC 8259 (`application/json`) and
      RFC 9512 (`application/yaml`); neither reference implementation
      consumed them.
- [x] Depth bound (32) is phrased as a SHOULD-recommendation with no
      implementation claim — the reference implementations currently
      enforce no bound (verified 2026-07-03); wording matches
      Specification Section 24.3.
- [x] Security considerations mirror Specification Section 24
      (single source; template summarizes).
- [x] Line-ending statement matches Specification Section 11.2.
- [ ] Any concerns about the provisional-vs-standards wording.

## Expected Process After Sending

1. **Acknowledgment** from the mailing list usually within 1–3 days.
2. **Public review period** of at least two weeks; any member of the
   mailing list may raise concerns.
3. **Designated Expert** (currently appointed through the IESG) may ask
   clarifying questions or suggest wording changes. These are typically
   minor (e.g., tighten a security paragraph, clarify a parameter).
4. **Registration** in the IANA Media Types registry, after which
   `application/jmd` is listed at:
       https://www.iana.org/assignments/media-types/media-types.xhtml

Typical end-to-end time: 2 to 6 weeks.

## Notes on the Structured Syntax Suffix `+jmd`

A separate registration request for the structured syntax suffix `+jmd`
(analogous to `+json`, `+xml`, `+yaml`) can be submitted in parallel or
after the main type registration is approved. The procedure is the same
e-mail list, but the template differs (RFC 6839). This document does
not include the `+jmd` suffix template; it can be prepared later if
desired.

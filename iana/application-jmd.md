# IANA Media Type Registration: `application/jmd`

**Purpose of this document.** This is a provisional registration request
for the media type `application/jmd`, following the template defined in
RFC 6838 §5.6. It is prepared for submission to `media-types@iana.org`
under the Provisional Registration procedure (RFC 6838 §5.3).

**Upgrade path.** Once an Internet-Draft describing JMD is published by
the IETF or another recognized standards body, this registration may be
promoted from provisional to permanent under the Standards Tree.

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
    charset:
        A charset parameter indicating the character encoding of the
        document. The only supported charset is "utf-8"; this is also
        the default when the parameter is omitted. Receivers MAY reject
        any other value with a 415 Unsupported Media Type response (for
        HTTP transport) or an equivalent error condition.

    version:
        An optional parameter carrying the JMD Specification version
        targeted by the document (e.g., "0.3.2"). When omitted, the
        receiver SHOULD assume the latest stable JMD specification
        version it supports.

Encoding considerations:
    JMD is a text format and MUST be encoded as UTF-8 (RFC 3629).
    Documents consisting entirely of ASCII characters are 7-bit safe;
    documents containing non-ASCII UTF-8 byte sequences require 8-bit
    transport. Content-Transfer-Encoding values such as "base64" or
    "quoted-printable" are permitted for transport systems that require
    7-bit encoding (such as historical e-mail), but are neither
    necessary nor recommended for modern HTTP or MCP transport.

Security considerations:
    JMD inherits the security posture of "application/json". Specific
    considerations:

    1.  Injection into downstream rendering contexts. JMD string
        content is literal data, but documents may contain characters
        that are structurally significant in downstream contexts
        (HTML, SQL, shell). Receivers that render JMD content into
        such contexts MUST apply the appropriate escaping. This is
        identical to the JSON situation and is not specific to JMD.

    2.  Parser resource consumption. A conforming JMD parser processes
        documents in O(n) time and O(d) stack depth, where n is the
        document length in bytes and d is the maximum heading depth.
        Implementations SHOULD enforce a practical bound on d (a
        reasonable default is 32) to prevent stack exhaustion from
        adversarial inputs. Line length, blockquote length, and field
        count have no inherent bound in the grammar, and
        implementations SHOULD impose application-specific limits
        consistent with their memory budget.

    3.  Content confusion with Markdown. JMD and conventional Markdown
        share a syntactic subset (headings, bullets, blockquotes).
        A receiver that renders a JMD document as Markdown will produce
        a document that is technically well-formed but semantically
        nonsensical (data fields become apparent section headings and
        bullet lists). Implementations MUST dispatch on the declared
        Content-Type and not on file content sniffing.

    4.  No active content. JMD has no scripting, no template
        expansion, no external reference resolution, no schema
        validation directives, and no anchor/alias mechanism. Parsing
        a JMD document does not trigger network access, code
        execution, or arbitrary I/O. This is identical to the JSON
        security model.

    5.  Privacy. JMD documents are opaque structured data. They do not
        carry fragment identifiers, external references, or embedded
        URIs that are interpreted implicitly by a conforming parser.
        Any URI-valued fields are application-level data; no JMD
        parser is required to follow them.

    6.  Streaming parse semantics. JMD is line-oriented and every
        completed line is independently parseable. This means that a
        partial JMD document may be partially processed by a receiver
        before the full document has arrived. Implementations that act
        on streaming data before the document is complete MUST ensure
        that such actions are safe under truncation (for example, a
        database write that commits only when the document terminator
        is observed).

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

    Line-ending handling: a conforming parser accepts "\n", "\r\n",
    and "\r" as line terminators. Canonical form uses "\n".

Published specification:
    JMD Specification v0.3.2, available at:
        https://github.com/ostermeyer/jmd-spec/blob/main/jmd-spec-v0_3.md

    A companion proposal for HTTP integration is available at:
        https://github.com/ostermeyer/jmd-spec/blob/main/jmd-over-http.md

    An Internet-Draft describing JMD is in preparation and will be
    submitted to the IETF Datatracker. This registration request
    should be treated as provisional until the Internet-Draft is
    published, at which point the registration can be promoted under
    the Specification Required or Standards Action procedures.

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
      expected files.
- [ ] The contact e-mail is current.
- [ ] The `charset` wording aligns with how the implementations actually
      behave (reject non-UTF-8, or accept?).
- [ ] The depth bound mentioned in security considerations (32) matches
      what the reference implementations enforce, or a reasonable value
      you want to recommend.
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

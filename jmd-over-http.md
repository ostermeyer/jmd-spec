# JMD over HTTP — REST Integration Proposal

**Status:** Proposal / Draft
**Version:** 0.1 (tracks JMD Specification v0.3.3)
**Copyright** © 2026 Andreas Ostermeyer <andreas@ostermeyer.de>
**License:** CC BY 4.0 (same as the JMD Specification)

---

## Abstract

This document proposes a set of conventions for using JMD (JSON Markdown, see the core specification) as a first-class payload format over HTTP. It describes how the four canonical data operations — Create/Update, Read, Query, and Delete — can be mapped to HTTP methods and paths; how content negotiation allows a single endpoint to speak both JSON and JMD; how streaming responses work over chunked transfer encoding; and how errors, caching, idempotency, authentication, and versioning fit naturally into existing HTTP idioms.

**Everything in this document is a RECOMMENDATION (RFC 2119 SHOULD), not a requirement.** The goal is to show how JMD *can* be integrated into REST ecosystems cleanly and without friction — not to prescribe how it *must* be integrated. Implementers are invited to adopt, adapt, or disregard these conventions as their context requires, and to push back on any choice that does not serve their use case. Community feedback is the primary purpose of publishing this proposal.

---

## 1. Introduction

### 1.1 Purpose

The JMD core specification is deliberately transport-agnostic: it describes a document format, not a protocol. HTTP is by far the most common transport for structured data today, and many JMD use cases — MCP servers, REST APIs, agent-to-agent pipelines, content services — run over HTTP. A shared set of conventions for "JMD over HTTP" reduces friction in three directions:

- **Client-side implementers** know how to construct requests and interpret responses without guessing.
- **Server-side implementers** know which HTTP methods to bind to which operations, how to signal streaming, and how to handle content negotiation.
- **LLM agents** consuming the API can rely on predictable endpoints, which reduces tool-use errors and makes training data more consistent.

### 1.2 Scope

This document covers:

- Media-type definition and registration (`application/jmd`)
- Content negotiation between JMD and JSON
- HTTP method and path mapping for the four canonical operations
- Streaming over chunked transfer encoding
- Error handling with JMD error documents
- Caching, idempotency, conditional requests
- Authentication, CORS, versioning

This document does **not** cover:

- The JMD grammar itself (see the core specification)
- Non-HTTP transports (MCP is discussed briefly where relevant, but the primary MCP integration is addressed by the MCP protocol itself; see core spec §18.5)
- Framework-specific plugin implementations (FastAPI, Express, Rails, etc.) — those belong in cookbook-style companion material, not in a protocol proposal

### 1.3 Status and Stability

This is a **proposal**. Every convention described here is tentative. We have chosen concrete values (path suffixes, header names, status codes) so that early implementers have something to build against — but these choices are subject to change based on community feedback. Section 13 lists the specific points where input is most welcome.

### 1.4 Conformance Language

The key words *MUST*, *MUST NOT*, *SHOULD*, *SHOULD NOT*, *MAY* are used in the sense of RFC 2119, but as already stated: **this document as a whole is a SHOULD**. Nothing within it rises to MUST for conformance with the core JMD specification. An implementation that uses JMD over HTTP in a way entirely different from what is proposed here is still conformant to the core spec — it simply does not use these conventions.

---

## 2. Media Type

### 2.1 Proposed Registration: `application/jmd`

We propose registering the media type `application/jmd` with IANA, using the following template (RFC 6838):

| Field | Value |
|---|---|
| Type name | `application` |
| Subtype name | `jmd` |
| Required parameters | *none* |
| Optional parameters | `charset` (default: `utf-8`), `version` (default: latest stable JMD spec) |
| Encoding considerations | Text; UTF-8 strongly recommended |
| Security considerations | Analogous to `application/json`; see §2.3 |
| Interoperability considerations | See §2.2 regarding fallback to JSON |
| Published specification | JMD Specification (latest), plus this document |
| Applications using this media type | LLM-to-server communication, MCP servers, REST APIs, streaming data pipelines, configuration files, service-to-service structured data exchange |
| Fragment identifier considerations | None defined by this specification |
| Restrictions on usage | None |
| Provisional registration | Yes (during proposal phase) |

Until registration is complete, the type may be used as `application/vnd.jmd` or `application/x-jmd` by early implementers who prefer to avoid the unqualified form. We recommend the unqualified `application/jmd` as the target name.

### 2.2 Structured Syntax Suffix

Analogous to `application/vnd.example+json`, we propose the structured syntax suffix `+jmd` for domain-specific JMD types:

```
application/vnd.example.order+jmd
application/vnd.ostermeyer.smartsuite.record+jmd
```

A generic JMD parser recognises any media type ending in `+jmd` as structurally equivalent to `application/jmd`, allowing domain-specific types to declare their schema without requiring consumers to learn a new parser.

### 2.3 Security Considerations

JMD inherits the security posture of `application/json` with one addition: because JMD permits prose in certain fields (blockquote multiline values, frontmatter text fields), implementations that render these fields to HTML without escaping are vulnerable to injection attacks in the same way that a JSON-carrying application would be. The mitigation is identical: treat string content as data, not markup, at every rendering boundary.

JMD has no constructs analogous to YAML's anchor/alias mechanism or JSON-LD's `@context`, so there are no implicit reference-following or schema-loading attack surfaces. Parsers are line-oriented and stateless beyond the heading-depth stack — there is no ambient context to poison.

---

## 3. Content Negotiation

### 3.1 Request-Side Negotiation

A client that wishes to receive a JMD response sends an `Accept` header:

```http
GET /orders/42 HTTP/1.1
Host: api.example.com
Accept: application/jmd
```

A client that accepts both JSON and JMD with a preference expresses this via quality values (RFC 7231 §5.3.1):

```http
Accept: application/jmd;q=1.0, application/json;q=0.9
```

Or, for a client that prefers JMD but cannot refuse JSON:

```http
Accept: application/jmd, application/json;q=0.5, */*;q=0.1
```

### 3.2 Server-Side Behaviour

A server that supports both content types:

- Parses the `Accept` header and selects the highest-preference supported type.
- Returns the selected representation with an explicit `Content-Type` header.
- Includes `Vary: Accept` so that caches correctly distinguish JSON and JMD responses for the same URL.

A server that does not support `application/jmd` SHOULD respond with `406 Not Acceptable` if the client explicitly requested JMD and accepts nothing else. A server that defaults to JSON when no `Accept` header is present behaves as today's JSON APIs do.

### 3.3 Request Body Content Types

A client that sends a JMD request body declares it via `Content-Type`:

```http
POST /orders HTTP/1.1
Host: api.example.com
Content-Type: application/jmd
Accept: application/jmd

# Order
customer: 42
total: 84.99
```

A server that accepts both JSON and JMD request bodies parses based on the `Content-Type` header of the incoming request. Mixed-content interactions (client sends JSON, server returns JMD, or vice versa) are fully supported — the two are semantically equivalent.

### 3.4 Content Coding (Compression)

Standard HTTP content codings (`gzip`, `deflate`, `br`) apply to JMD exactly as they do to JSON. JMD compresses somewhat less aggressively than pretty-printed JSON — there are fewer redundant characters to eliminate — but the absolute compressed size is comparable, and the CPU cost of compression and decompression is the same. `Accept-Encoding` and `Content-Encoding` operate independently of content negotiation between JMD and JSON.

---

## 4. HTTP Method and Path Mapping

### 4.1 The Core Mapping

The four canonical JMD operations map to HTTP methods and path conventions as follows:

| Operation | HTTP Method | Path | Request Body | Response Body | Success Status |
|---|---|---|---|---|---|
| **Read** (single resource) | `GET` | `/resource/{id}` | — | `# ResourceLabel` | `200 OK` |
| **Read** (collection) | `GET` | `/resource` | — | `# []` or `# Collection` | `200 OK` |
| **Query** | `POST` | `/resource/$query` | `#? ResourceLabel` | `# []` | `200 OK` |
| **Create** | `POST` | `/resource` | `# ResourceLabel` | `# ResourceLabel` (created) | `201 Created` |
| **Update** (full) | `PUT` | `/resource/{id}` | `# ResourceLabel` | `# ResourceLabel` (updated) | `200 OK` |
| **Update** (partial) | `PATCH` | `/resource/{id}` | `# ResourceLabel` (delta) | `# ResourceLabel` (updated) | `200 OK` |
| **Delete** (single) | `DELETE` | `/resource/{id}` | — | — or confirmation | `204 No Content` |
| **Delete** (bulk) | `POST` | `/resource/$delete` | `#- []` | — or confirmation | `200 OK` / `204` |
| **Schema** (fetch) | `GET` | `/resource/$schema` | — | `#! ResourceLabel` | `200 OK` |

This mapping preserves HTTP semantics as much as possible:

- `GET` is safe and idempotent (read, read-collection, schema fetch).
- `PUT` is idempotent (full replacement of a resource).
- `DELETE` is idempotent (remove a resource — calling twice yields the same end state).
- `POST` covers non-idempotent operations (create, query, bulk delete).
- `PATCH` covers partial updates.

### 4.2 Query over POST, Not GET

We propose `POST /resource/$query` with the query document as the request body, rather than encoding filter conditions in a GET query string. The rationale:

- Filter conditions can be rich and structured. QBE documents include nested arrays, multiple fields, and mode-specific syntax that does not fit naturally into URL query parameters.
- URL length limits vary across proxies, CDNs, and servers, commonly around 2000–8000 bytes. A non-trivial QBE query may exceed these limits.
- The request body is already JMD-native — the same format the client is learning for data. Introducing a secondary URL-parameter encoding for filters would create a second dialect to master.
- `POST` is the correct HTTP method for operations whose semantic is "process this document". Query is such an operation.

**Trade-off with HTTP caching:** `POST` is not cached by default. For read-heavy query workloads where caching matters, a server MAY expose additional `GET`-based specialized endpoints (e.g., `GET /orders?status=pending&page-size=50`), either alongside or instead of the generic `$query` endpoint. Such endpoints are application-specific and out of scope for this proposal.

**Alternatives considered:**

| Alternative | Pro | Con |
|---|---|---|
| `GET /resource?q=...` with URL-encoded query | Cacheable by default | URL length limits; dual-format learning curve |
| `GET /resource` with body (non-standard) | Stays with `GET` semantically | Violates RFC 7231; many proxies strip the body |
| `QUERY` method (RFC 9205 / HTTP extension) | Semantically precise | Not widely implemented; breaks with legacy infrastructure |
| `POST /resource/$query` (this proposal) | Standards-compliant, body-capable | Not cached by default |

### 4.3 Bulk Delete over POST

`DELETE` with a request body is syntactically permitted by RFC 7231 but semantically controversial: many proxies, CDNs, and HTTP libraries strip the body from `DELETE` requests, on the assumption that the operation's target is fully identified by the URL.

We therefore propose that **bulk delete** (removing multiple resources identified by a JMD `#-` document) uses `POST /resource/$delete` with the delete document as the body, rather than `DELETE /resource` with a body. Single-resource delete continues to use the natural `DELETE /resource/{id}` with no body.

**Alternatives considered:**

| Alternative | Pro | Con |
|---|---|---|
| `DELETE /resource` with body | Method matches intent | Body-stripping in infrastructure |
| `POST /resource/$delete` (this proposal) | Works across all infrastructure | Method does not name the intent |
| `DELETE /resource?ids=1,2,3` | No body; method matches | URL length limits; escaping complexity |

### 4.4 Schema Fetch

We propose `GET /resource/$schema` as the canonical way to retrieve the schema document describing the shape of a resource.

**Alternatives considered:**

| Alternative | Pro | Con |
|---|---|---|
| `GET /resource/$schema` (this proposal) | Discoverable; uses same `$` convention as `$query`, `$delete` | Introduces a path suffix |
| `OPTIONS /resource` with schema in body | Uses existing HTTP method | `OPTIONS` body conventions are not standardised |
| `Link` header on `GET /resource` responses with `rel="describedby"` pointing to a schema URL | Purely header-based, no new endpoint | Two round-trips; client must follow link |

The proposed form is discoverable (a client that sees `$query` and `$delete` endpoints can reasonably guess `$schema`) and consistent with the other path-suffix conventions. Servers that prefer the `Link` header approach remain fully conformant — this is a recommendation, not a requirement.

### 4.5 Path Suffix Convention: The `$` Prefix

Operations that do not map naturally to a simple resource path use the `$`-prefix suffix convention: `/resource/$query`, `/resource/$delete`, `/resource/$schema`, `/resource/$stream`. The prefix character serves to visually separate operation paths from resource identifiers:

```
/orders/42         — resource ID 42
/orders/$query     — the query operation on the orders collection
```

The `$` character is reserved in URLs (RFC 3986 §2.2), but it is allowed in path segments without percent-encoding and is widely used in existing APIs (Firebase, JSON:API, OData). Using it as a prefix makes operation endpoints visually unambiguous and avoids collision with resource IDs that would otherwise need naming discipline.

**Alternatives considered:**

| Alternative | Pro | Con |
|---|---|---|
| `$`-suffix paths (this proposal) | Visually distinct from resource IDs | Not immediately familiar to all developers |
| `/resource/_query`, `/resource/_delete` | All-ASCII; no reserved characters | Underscore is a valid resource-ID character in many schemes — collision risk |
| `/resource:query`, `/resource:delete` | Single-segment, no slash | Colon has special meaning in some URL parsers |
| `?op=query` query parameter | No path-level discrimination | Mixes operation with filter parameters; harder to route |

### 4.6 Method Mapping Summary

The proposed mapping is deliberately a union of "most HTTP-idiomatic" and "most JMD-operationally honest". It deviates from strict REST only where JMD's operational model (which has `query` as a first-class operation, distinct from `read`) exceeds what vanilla REST provides.

---

## 5. Streaming

### 5.1 Why Streaming Matters

JMD is line-oriented by design. Every completed line of a JMD document is an independent semantic event (see core spec §18). HTTP chunked transfer encoding delivers exactly this property at the transport layer: each chunk is independently parseable and actionable by the client.

The combination — JMD documents flowing over chunked HTTP responses — makes time-to-first-useful-data (TTFUB) a function of when the first *record* is ready, not when the *entire response* is assembled. For large collection queries this changes the perceived latency profile fundamentally.

### 5.2 Transfer-Encoding

A streaming JMD response uses standard HTTP chunked transfer encoding:

```http
HTTP/1.1 200 OK
Content-Type: application/jmd
Transfer-Encoding: chunked
X-JMD-Streaming: true

# []
- id: 1
  status: pending
- id: 2
  status: active
...
```

Each JMD line maps naturally to a chunk boundary, though servers MAY batch multiple lines into a single chunk for efficiency. The client's JMD parser fires events as chunks arrive; no application-level framing is required.

### 5.3 The `X-JMD-Streaming` Header

We propose a response header `X-JMD-Streaming: true` as an **advisory signal** that the server is producing the response incrementally. The header tells the client that the streaming JMD parser should be used instead of buffering the entire body.

This header is advisory only; a client MAY use the streaming parser on any JMD response regardless of the header. The header exists to help clients that want to choose between a buffering and streaming parse path based on server behaviour.

### 5.4 Early Termination

Because each JMD line is independently processable, a client that has seen enough may close the TCP connection at any chunk boundary. The server detects the close and stops generating further output. This is particularly valuable for large-result queries where the client may only need the first few records.

Servers SHOULD be prepared for client-initiated early termination and SHOULD NOT treat it as an error condition — it is a valid and expected pattern for LLM-driven query clients that find their answer quickly.

### 5.5 Server-Sent Events (SSE) Alternative

For push-based or long-lived scenarios (live dashboards, agent tool output streamed as it is generated), Server-Sent Events with JMD payloads is a natural fit. The core specification §18.4 describes the composition; a summary:

```http
Content-Type: text/event-stream
```

```
data: # Order
data: id: 42
data: status: pending
data:
```

The blank `data:` line terminates the SSE event. Each event carries one complete JMD document. For high-frequency, single-field updates, the SSE event may carry one JMD line instead of a whole document; the client reassembles the stream.

### 5.6 Middleware Buffering

As the core specification §18.2b notes, streaming is only end-to-end if every hop supports it. A middleware server that translates from a buffered backend (e.g., a JSON-returning database driver) to a JMD client cannot stream beyond what the backend delivers. This is not a defect in JMD; it is an intrinsic property of any format bridge that translates between buffered and streaming representations. JMD-native backends avoid this limitation entirely.

---

## 6. Error Handling

### 6.1 HTTP Status vs. JMD Error Document

HTTP status codes remain the primary signal for request outcome. A response status in the 4xx/5xx range indicates a failure; the response body, if any, carries a JMD error document (core spec §17):

```http
HTTP/1.1 404 Not Found
Content-Type: application/jmd

# Error
status: 404
code: not_found
message: Order 42 not found.
```

The `status` field in the JMD error document echoes the HTTP status code. This redundancy is deliberate: it allows the error document to travel across transports (HTTP → MCP relay → agent) without losing the status information that a non-HTTP consumer cannot read from headers.

### 6.2 Status Code Recommendations

| HTTP Status | JMD `code` (suggestion) | When |
|---|---|---|
| `400 Bad Request` | `invalid_request` | Malformed JMD body, invalid frontmatter directive |
| `401 Unauthorized` | `unauthorized` | Missing or invalid credentials |
| `403 Forbidden` | `forbidden` | Valid credentials but insufficient permissions |
| `404 Not Found` | `not_found` | Resource or schema does not exist |
| `405 Method Not Allowed` | `method_not_allowed` | Method not supported for this path |
| `406 Not Acceptable` | `not_acceptable` | Client requested JMD but server only offers JSON |
| `409 Conflict` | `conflict` | Write conflicts with current resource state (e.g., ETag mismatch) |
| `410 Gone` | `gone` | Resource existed but has been deleted permanently |
| `412 Precondition Failed` | `precondition_failed` | `If-Match` or similar conditional header failed |
| `415 Unsupported Media Type` | `unsupported_media_type` | Request body content type not accepted by server |
| `422 Unprocessable Entity` | `validation_failed` | Body is syntactically valid JMD but semantically invalid |
| `429 Too Many Requests` | `rate_limited` | Rate limit exceeded |
| `500 Internal Server Error` | `internal_error` | Unhandled server error |
| `503 Service Unavailable` | `unavailable` | Service temporarily down |

The `code` column is a **suggestion**. The error code vocabulary is application-specific and will converge through usage patterns rather than top-down standardisation — the core spec §17 rationale explicitly declines to mandate a fixed code enumeration.

### 6.3 Streaming Errors

If a server encounters an error after it has already begun emitting a streaming response, it SHOULD emit a JMD error document at the end of the partial stream:

```
# []
- id: 1
  status: pending
- id: 2
  status: active

# Error
status: 500
code: internal_error
message: Backend connection lost after row 2.
```

The stream-then-error pattern allows the client to retain the data it has already received while understanding that the stream did not complete. Clients SHOULD treat a trailing `# Error` document as a termination signal and a diagnostic, not as a reason to discard the partial data.

### 6.4 Non-Fatal Warnings

For non-fatal conditions (deprecation notices, partial failures in bulk operations, quota warnings), the server MAY use response frontmatter rather than an error document:

```
deprecated-path: true
rate-limit-remaining: 42

# []
...
```

This preserves the success semantic (status 200) while still surfacing advisory information through the frontmatter channel.

---

## 7. Caching, Idempotency, Conditional Requests

### 7.1 ETag Support

Responses to `GET` requests SHOULD include an `ETag` header identifying the current version of the resource:

```http
HTTP/1.1 200 OK
Content-Type: application/jmd
ETag: "v27-3af82b"

# Order
id: 42
...
```

Clients cache the response and, on subsequent reads, issue conditional requests:

```http
GET /orders/42 HTTP/1.1
If-None-Match: "v27-3af82b"
```

A server that sees the current version matches responds with `304 Not Modified` and no body. This works unchanged for JMD as it does for JSON.

### 7.2 Conditional Updates

For updates, `If-Match` protects against lost-update scenarios:

```http
PUT /orders/42 HTTP/1.1
Content-Type: application/jmd
If-Match: "v27-3af82b"

# Order
id: 42
status: shipped
```

A server that sees the version has moved on responds with `412 Precondition Failed` and a JMD error document describing the conflict.

### 7.3 Idempotency Keys

For `POST` operations — create, query (if the application treats repeated queries as cache hits), and bulk delete — a client that wants retry-safe semantics includes an `Idempotency-Key` header with a unique identifier:

```http
POST /orders HTTP/1.1
Content-Type: application/jmd
Idempotency-Key: 8f3a7e-9c12-... 

# Order
customer: 42
```

A server that sees the same key twice within its retention window returns the same response as the first time, without re-executing the operation. This is the Stripe-style idempotency pattern and is orthogonal to JMD; we merely note that it applies unchanged.

### 7.4 `Vary` Header

Because content negotiation chooses between JSON and JMD based on `Accept`, caches must key on `Accept` to avoid serving the wrong representation. Servers SHOULD include `Vary: Accept` on every response produced by content negotiation.

---

## 8. Authentication and CORS

### 8.1 Authentication

JMD over HTTP uses the same authentication mechanisms as any other HTTP API:

- Bearer tokens in the `Authorization` header
- Cookie-based sessions
- API keys in a custom header (`X-API-Key` or similar)
- mTLS at the transport layer

None of these interact with the payload format. A JMD request is authenticated in exactly the same way as a JSON request.

### 8.2 CORS

Cross-Origin Resource Sharing (RFC 6454, W3C CORS spec) applies to JMD endpoints exactly as it does to JSON endpoints. Preflight `OPTIONS` responses SHOULD include `application/jmd` in `Access-Control-Allow-Headers` (for `Content-Type`) if the endpoint accepts JMD request bodies:

```http
Access-Control-Allow-Origin: https://client.example.com
Access-Control-Allow-Methods: GET, POST, PUT, PATCH, DELETE
Access-Control-Allow-Headers: Content-Type, Authorization, If-Match, Idempotency-Key
Access-Control-Expose-Headers: ETag, X-JMD-Streaming
```

`X-JMD-Streaming` in `Access-Control-Expose-Headers` is advisable because the header is meant to be read by the client; without exposure, browser clients cannot see it.

---

## 9. Versioning

JMD version negotiation is proposed via media-type parameters rather than URL paths or custom headers.

### 9.1 Media-Type Parameter

A client that requires a specific JMD version includes it in `Accept`:

```http
Accept: application/jmd;version=0.3
```

A server that supports multiple versions responds with the selected version in `Content-Type`:

```http
Content-Type: application/jmd;version=0.3
```

If the client's required version is not supported, the server responds with `406 Not Acceptable`.

### 9.2 Default Version

In the absence of a `version` parameter, server and client SHOULD default to the latest stable JMD specification. Servers MAY pin to a specific version if they are not prepared to accept future JMD versions without testing.

### 9.3 Why Not URL Path Versioning (`/v1/orders`)?

URL path versioning is common in existing APIs but has drawbacks for JMD:

- It conflates the API's own version with JMD's format version.
- It requires all routes to be duplicated for each version.
- It breaks caching and content negotiation hierarchy.

The media-type parameter form keeps JMD format versioning orthogonal to API versioning — an API at `/v2/` can speak JMD 0.3 or JMD 0.4 independently.

### 9.4 API Versioning

This proposal does not specify how the API's own version (as distinct from the JMD format version) is expressed. Common patterns remain available:

- URL path: `/v1/orders`, `/v2/orders`
- Media type: `application/vnd.example.v1+jmd`
- Header: `X-API-Version: 1`

All three are compatible with JMD. The choice is application-level and orthogonal to this proposal.

---

## 10. Complete Examples

### 10.1 Read a Single Resource

**Request:**

```http
GET /orders/42 HTTP/1.1
Host: api.example.com
Accept: application/jmd
```

**Response:**

```http
HTTP/1.1 200 OK
Content-Type: application/jmd
ETag: "v27-3af82b"
Vary: Accept

# Order
id: 42
status: pending
customer: 18
total: 84.99
## address
street: Hauptstraße 1
city: Berlin
zip: "10115"
country: DE
## items[]
- sku: A1
  qty: 2
  price: 29.99
- sku: B3
  qty: 1
  price: 24.99
```

### 10.2 Query with Streaming

**Request:**

```http
POST /orders/$query HTTP/1.1
Host: api.example.com
Content-Type: application/jmd
Accept: application/jmd

page-size: 50

#? Order
status: pending
total: > 50
```

**Response:**

```http
HTTP/1.1 200 OK
Content-Type: application/jmd
Transfer-Encoding: chunked
X-JMD-Streaming: true
Vary: Accept

total: 4832
page: 1
pages: 97
page-size: 50

# []
- id: 1
  status: pending
  total: 84.99
- id: 7
  status: pending
  total: 120.00
- id: 12
  status: pending
  total: 67.50
...
```

The client sees `total: 4832` before any record arrives — enough information to narrow the query or page through results without consuming the full first page.

### 10.3 Create a Resource

**Request:**

```http
POST /orders HTTP/1.1
Host: api.example.com
Content-Type: application/jmd
Accept: application/jmd
Idempotency-Key: 8f3a7e9c-12d4-4b5e-ae67-0123456789ab

# Order
customer: 18
## items[]
- sku: A1
  qty: 3
  price: 29.99
```

**Response:**

```http
HTTP/1.1 201 Created
Content-Type: application/jmd
Location: /orders/87
ETag: "v1-7c0f49"

# Order
id: 87
status: new
customer: 18
total: 89.97
created_at: "2026-04-16T10:22:14Z"
## items[]
- sku: A1
  qty: 3
  price: 29.99
```

### 10.4 Conditional Update

**Request:**

```http
PUT /orders/87 HTTP/1.1
Host: api.example.com
Content-Type: application/jmd
Accept: application/jmd
If-Match: "v1-7c0f49"

# Order
id: 87
status: confirmed
customer: 18
## items[]
- sku: A1
  qty: 3
  price: 29.99
```

**Response (successful):**

```http
HTTP/1.1 200 OK
Content-Type: application/jmd
ETag: "v2-3e81a0"

# Order
id: 87
status: confirmed
...
```

**Response (conflict):**

```http
HTTP/1.1 412 Precondition Failed
Content-Type: application/jmd

# Error
status: 412
code: precondition_failed
message: The order has been modified since you last read it.
current-version: "v2-3e81a0"
```

### 10.5 Bulk Delete

**Request:**

```http
POST /orders/$delete HTTP/1.1
Host: api.example.com
Content-Type: application/jmd
Accept: application/jmd

#- []
- 42
- 87
- 103
```

**Response:**

```http
HTTP/1.1 200 OK
Content-Type: application/jmd

# Result
deleted: 3
## deleted-ids[]
- 42
- 87
- 103
```

### 10.6 Schema Retrieval

**Request:**

```http
GET /orders/$schema HTTP/1.1
Host: api.example.com
Accept: application/jmd
```

**Response:**

```http
HTTP/1.1 200 OK
Content-Type: application/jmd
Cache-Control: max-age=3600

#! Order
id: integer readonly
status: new|confirmed|shipped|cancelled = new
customer: -> Customer
total: number readonly
created_at: string datetime readonly

## items[]: object
- sku: string
  qty: integer
  price: number
```

Note: the content of schema values (`integer readonly`, `-> Customer`, `number`) is opaque to JMD — the application interprets these strings according to its own type conventions (see core spec §14 and Appendix A.2).

---

## 11. Implementation Notes

### 11.1 Middleware Pattern

The cleanest integration pattern for existing JSON-based services is a **format-translation middleware**: a layer that accepts JMD requests, translates to JSON for the existing backend, and translates JSON responses back to JMD on the way out.

```
Client  ←[JMD]→  Middleware  ←[JSON]→  Backend
```

For streaming responses, this middleware must buffer the full JSON response before emitting JMD (core spec §18.2b) — the streaming advantage is lost until the backend speaks JMD natively. For non-streaming responses, the middleware is a ~100-line adapter per framework.

### 11.2 Native Backend

A backend that reads and writes JMD directly — e.g., a database driver that streams rows as JMD items, or an LLM tool server that emits JMD as it generates — realises the full streaming advantage. This is the target state for new JMD-native systems.

### 11.3 OpenAPI Compatibility

OpenAPI 3.x documents can describe JMD endpoints by using `application/jmd` in `content` fields. Schema references still use JSON Schema (OpenAPI's native schema language); the fact that the transport payload is JMD rather than JSON does not require a change to the schema tooling. A future OpenAPI extension could directly embed JMD schema documents, but this proposal does not require it.

---

## 12. Relationship to Other Specifications

| Spec | Relationship |
|---|---|
| [RFC 7230–7237](https://www.rfc-editor.org/info/rfc7230) (HTTP/1.1) | This document applies unchanged. |
| [RFC 9110](https://www.rfc-editor.org/info/rfc9110) (HTTP Semantics) | This document applies unchanged. |
| [RFC 6838](https://www.rfc-editor.org/info/rfc6838) (Media Type Specifications) | §2 of this document follows. |
| [RFC 6455](https://www.rfc-editor.org/info/rfc6455) (WebSocket) | Out of scope; JMD over WebSocket is a separate concern. |
| HTML5 [SSE spec](https://html.spec.whatwg.org/multipage/server-sent-events.html) | Referenced in §5.5; composable with JMD. |
| OData | JMD's `->` reference convention (Appendix A.2.6) and `$expand` frontmatter (core spec §23.5) are inspired by OData's NavigationProperties, but JMD does not import the full OData model. |
| JSON:API | JMD is a format; JSON:API is a protocol. The two can coexist — a JSON:API server can offer JMD representations via content negotiation. |
| GraphQL | Orthogonal. GraphQL uses a single endpoint with a query body; JMD over REST uses resource-oriented endpoints with document bodies. The two models target different design aesthetics and can coexist within the same organisation. |

---

## 13. Open Questions for Community Input

This is the list of points where we most want implementer feedback before any of the conventions above are treated as stable. If you are building on JMD-over-HTTP, we want to hear from you on:

1. **Path suffix choice** (§4.5). Is the `$` prefix the right convention for operation paths, or would `_` or a distinct path segment (`/$op/query` vs. `/$query`) serve better in your infrastructure?

2. **Query over POST** (§4.2). Does the loss of default caching on query responses hurt enough that you would want GET-based query specializations standardized? If yes, what URL-parameter dialect would you propose?

3. **Bulk delete** (§4.3). Is `POST /$delete` preferable over `DELETE` with a body in your infrastructure? Have you encountered proxies or CDNs that strip `DELETE` bodies?

4. **Streaming header name** (§5.3). Is `X-JMD-Streaming` a good name? Should it carry more information (e.g., record count when known, or chunk boundary hints)?

5. **Error code vocabulary** (§6.2). Would a more rigorous standard code vocabulary be useful, or does the current application-specific approach fit your domain?

6. **Version parameter** (§9.1). Is `application/jmd;version=0.3` acceptable, or would you prefer a separate header such as `X-JMD-Version`?

7. **Schema endpoint** (§4.4). Is `GET /resource/$schema` the right shape, or would you prefer schema embedded in a response `Link` header?

8. **Non-CRUD operations** (not covered). If your domain includes operations that don't fit CRUD+Query (long-running jobs, approvals, transactions), how would you expose them via JMD/HTTP?

9. **Authentication specifics** (§8.1). Are there authentication patterns specific to JMD-based APIs that deserve a section — e.g., JMD-native capability tokens, or frontmatter-based identity hints?

10. **Framework-specific guidance**. Would you use a companion document (or set of documents) for FastAPI, Express, Rails, Spring integration examples, or does each framework's community handle this best on its own?

Feedback welcome via issues or pull requests on the JMD specification repository.

---

*This document will be revised based on community input. When v1.0 is reached, the stable conventions will be extracted into the core JMD specification or into a normative companion. Until then: this is a proposal, and nothing here is set in stone.*

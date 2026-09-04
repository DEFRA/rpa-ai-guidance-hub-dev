# Architecture

The RPA AI Guidance Hub across four views: system context, containers, the
API's components, and the data model. GitHub renders the diagrams below
natively; the mermaid source in this file is the source of truth.

The hub is two CDP services — `rpa-ai-guidance-hub-ui` and
`rpa-ai-guidance-hub-api` — with all backend functionality in the API
service. Content bytes live in object storage; MongoDB holds identity,
revisions, the link graph, review state and per-user state.

## System context (C1)

Three kinds of user, one system, three platform/external dependencies.

```mermaid
flowchart LR
  designer(["Designer"]):::actor --> hub
  approver(["Approver"]):::actor --> hub
  processor(["Processor"]):::actor --> hub
  hub["RPA AI Guidance Hub"]:::system
  hub --> entra["Defra Entra ID"]:::ext
  hub <--> uploader["CDP Uploader"]:::ext
  hub --> sites["External websites"]:::ext
  classDef actor fill:#f4f8fb,stroke:#0b0c0c,color:#0b0c0c
  classDef system fill:#008531,stroke:#008531,color:#ffffff
  classDef ext fill:#f3f2f1,stroke:#b1b4b6,color:#0b0c0c
```

- **Designer** authors, uploads and reviews guidance.
- **Approver** is the named approver for a guide: approves and publishes it.
- **Processor** finds and reads published guidance to process applications.
- **Defra Entra ID** provides sign-in; approver and author identities come
  from here.
- **CDP Uploader** is the platform's file transfer and virus scanning.
- **External websites** (GOV.UK and others) are link targets the hub
  checks periodically.

## Containers (C2)

```mermaid
flowchart TB
  designer(["Designer"]):::actor --> ui
  approver(["Approver"]):::actor --> ui
  processor(["Processor"]):::actor --> ui
  subgraph hub["RPA AI Guidance Hub"]
    ui["rpa-ai-guidance-hub-ui"]:::svc -->|"JSON/HTTPS"| api["rpa-ai-guidance-hub-api"]:::svc
    api --> mongo[("MongoDB")]:::store
    api --> s3[("Object storage - S3 via CDP")]:::store
  end
  ui --> entra["Defra Entra ID"]:::ext
  ui -->|"sends files to"| uploader["CDP Uploader"]:::ext
  api -->|"initiates uploads, polls scan status"| uploader
  api -->|"checks links against"| sites["External websites"]:::ext
  classDef actor fill:#f4f8fb,stroke:#0b0c0c,color:#0b0c0c
  classDef svc fill:#008531,stroke:#008531,color:#ffffff
  classDef store fill:#bbd4e6,stroke:#d2e2f1,color:#0b0c0c
  classDef ext fill:#f3f2f1,stroke:#b1b4b6,color:#0b0c0c
```

- **rpa-ai-guidance-hub-ui** — the interface: search and filters, the
  TipTap editor with quality checks, comments and version history beside
  it, drafts and approvals.
- **rpa-ai-guidance-hub-api** — the REST API. Workflow transitions are
  explicit actions (submit / approve / reject / publish / remove) so each
  invariant lives in one handler. Document conversion and link checking
  run inside this service too — there are no separate workers.

## API components (C3)

The component groups inside `rpa-ai-guidance-hub-api`, which are also the
API surface: one group per resource, plus the two internal jobs.

```mermaid
flowchart TB
  ui["rpa-ai-guidance-hub-ui"]:::svc --> finder & drafting & workflow & uploads & me
  subgraph api["rpa-ai-guidance-hub-api"]
    finder["Finder"]
    items["Items and versions"]
    drafting["Drafting"]
    workflow["Workflow"]
    uploads["Uploads"]
    quality["Quality"]
    comments["Comments"]
    linkGraph["Link graph"]
    me["Me"]
    conversion["Conversion"]
    linkCheck["Link checks"]
    uploads -->|"hands scanned documents to"| conversion
  end
  finder & items & workflow & quality & comments & linkGraph & me --> mongo[("MongoDB")]:::store
  drafting --> mongo
  drafting & conversion --> s3[("Object storage")]:::store
  conversion --> mongo
  linkCheck --> mongo
  linkCheck --> sites["External websites"]:::ext
  uploads -->|"initiates, polls"| uploader["CDP Uploader"]:::ext
  me --> entra["Defra Entra ID"]:::ext
  classDef svc fill:#008531,stroke:#008531,color:#ffffff
  classDef store fill:#bbd4e6,stroke:#d2e2f1,color:#0b0c0c
  classDef ext fill:#f3f2f1,stroke:#b1b4b6,color:#0b0c0c
```

| Component | Responsibility |
| --- | --- |
| Finder | `GET /guidance` — search and facets over published versions |
| Items and versions | Item, version history, item-level changes (owner, archive) |
| Drafting | Open draft, save content and metadata, restore a version. A save bundles its side effects: rebuild links, run quality checks, re-anchor comments |
| Workflow | submit / approve / reject / publish / remove — enforces owner-not-author and one-open-version |
| Uploads | Initiate with CDP Uploader, poll status, create a guide from the converted document |
| Quality | Check reports joined with durable verdict dispositions |
| Comments | Anchored review threads with resolved state |
| Link graph | Inbound "what links here", removal impact, link-picker suggest, external check results |
| Me | Person-keyed views: my drafts, my approvals, my saved guides |
| Conversion | Word to markdown (mammoth) after a clean scan |
| Link checks | Scheduled sweep of external links; writes reports |

## Data model

Crow's foot on the many side. `USER` is a directory identity from Entra,
not a stored collection.

```mermaid
erDiagram
  GUIDANCE ||--o{ GUIDANCE_VERSION : "has revisions"
  GUIDANCE_VERSION ||--o{ LINK : "owns edges"
  LINK }o--o| GUIDANCE : "targets item"
  GUIDANCE_VERSION ||--o{ LINK_CHECK_REPORT : "swept by"
  GUIDANCE ||--o{ COMMENT : "hosts threads"
  GUIDANCE_VERSION ||--o{ COMMENT : "written against"
  GUIDANCE_VERSION ||--o{ QUALITY_REPORT : "checked into"
  GUIDANCE_VERSION ||--o{ FINDING_DISPOSITION : "settled by"
  GUIDANCE ||--o{ USER_GUIDANCE : "saved as"
  USER ||--o{ USER_GUIDANCE : "saves"
  USER ||--o{ GUIDANCE : "owns and approves"
  USER ||--o{ GUIDANCE_VERSION : "authors"

  GUIDANCE {
    ObjectId _id PK
    string slug UK "stable identity - links target this"
    string owning_team "administrative home"
    person owner "approves and publishes"
    ObjectId published_version_id FK "live revision"
    ObjectId draft_version_id FK "open revision"
    datetime archived_at "item retirement"
  }

  GUIDANCE_VERSION {
    ObjectId _id PK
    ObjectId guidance_id FK
    int version_no
    enum status "draft / pending_approval / approved / published / removed"
    string title
    string summary
    object metadata "category, tags, review_date, guidance_type, currency"
    object source_asset "S3 original + scan_status"
    object markdown_asset "S3 markdown + converter"
    object workflow "authored, submitted, submitted_to, approved"
    array history "status trail - who, when"
  }

  LINK {
    ObjectId _id PK
    ObjectId from_version_id FK "owner - rebuilt on save"
    ObjectId from_guidance_id FK
    enum kind "internal / external"
    ObjectId to_guidance_id FK "internal target item"
    string external_url "external target"
    enum from_status "denormalised owner status"
  }

  LINK_CHECK_REPORT {
    ObjectId _id PK
    ObjectId version_id FK
    datetime checked_at
    array results "url, http_status, ok"
    int broken_count
  }

  COMMENT {
    ObjectId _id PK
    ObjectId guidance_id FK "thread home - outlives versions"
    ObjectId version_id FK "written against"
    person author "id + role"
    string body
    object anchor "quote, heading + attached / orphaned"
    enum status "open / resolved"
    string resolved_by
    datetime created_at
  }

  QUALITY_REPORT {
    ObjectId _id PK
    ObjectId version_id FK
    datetime checked_at
    string ruleset
    array findings "rule_id, severity, anchor, anchor_hash"
    object counts "denormalised - list pages read this"
  }

  FINDING_DISPOSITION {
    ObjectId _id PK
    ObjectId version_id FK "unique with rule_id + anchor_hash"
    string rule_id
    string anchor_hash "stable finding identity"
    enum verdict "fixed / wont_fix / false_positive"
    string comment
    string by
    datetime at
  }

  USER_GUIDANCE {
    ObjectId _id PK
    string user_id FK
    ObjectId guidance_id FK
    datetime saved_at
  }

  USER {
    string id PK "directory identity - not a collection"
    string name
  }
```

### Design notes

- **Derived vs durable.** `LINK` and `QUALITY_REPORT` are rebuildable
  caches — regenerated from markdown on every version save, never edited
  by hand. `COMMENT` and `FINDING_DISPOSITION` are human state: a save
  re-anchors comments (the anchor flips to orphaned when the passage is
  gone) and never deletes either. Dispositions join to findings on
  `(version_id, rule_id, anchor_hash)`, so a re-run never resurrects a
  settled finding.
- **Person-keyed views.** *My approvals* is
  `status: pending_approval` + `workflow.submitted_to.id`, denormalised
  from `GUIDANCE.owner` at submit time. *My drafts* is the latest version
  per item where `workflow.authored_by.id` is me. *My saved guides* is
  `USER_GUIDANCE` by `user_id`, newest first.
- **Invariants (enforced in code).** At most one published and one open
  version per item. The owner is never the author of a version they
  approve. Changing an item's owner re-points `submitted_to` on its open
  submissions in the same write. Internal links resolve
  `to_guidance_id` → that item's published version at render time.
  Archiving a guide cleans or tombstones its `USER_GUIDANCE` rows.

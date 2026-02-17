# WhatsApp Archive Viewer - Technical Research

## Project Goal

Build a web application to search and browse 11+ years of WhatsApp conversations extracted from a rooted Android phone. The app must support:

- **Multilingual full-text search** (English, Russian, Hebrew) with substring/partial matching
- **Per-conversation and global search**
- **Media display** (images, audio playback, video thumbnails, documents)
- **Database merging** (import new dumps over time, deduplicate)
- **Authentication** (Google OAuth, granular access control)

---

## Part 1: WhatsApp Database Structure

### Database Files

All databases are located at `/data/data/com.whatsapp/databases/` on rooted Android:

| Database | Purpose |
|----------|---------|
| `msgstore.db` | Main message store: all messages, calls, media refs, chat list |
| `wa.db` | Contacts: phone numbers, display names, profile info |
| `axolotl.db` | Signal Protocol encryption keys (not needed for viewer) |
| `stickers.db` | Sticker packs |
| `location.db` | Shared/live locations |
| `media.db` | Media file metadata |

### Schema Versions (Critical)

WhatsApp underwent a **major schema overhaul around mid-2022** (v2.22.7.73):

| Aspect | Old Schema (pre-2022) | New Schema (2022+) |
|--------|----------------------|---------------------|
| Message table | `messages` (plural) | `message` (singular) |
| Text column | `data` | `text_data` |
| Chat reference | `key_remote_jid` (text JID) | `chat_row_id` (integer FK) |
| Sender in groups | `remote_resource` (text JID) | `sender_jid_row_id` (integer FK) |
| Direction flag | `key_from_me` | `from_me` |
| Type column | `media_wa_type` | `message_type` |
| Chat list | `chat_list` | `chat` + `chat_view` |
| Media | Inline in messages table | Separate `message_media` table |
| Quoted msgs | `messages_quotes` + `quoted_row_id` | `message_quoted` + related tables |

**Implication**: Our importer must detect which schema version a database uses and handle both.

### New Schema - Key Tables

#### `jid` - Central identifier lookup
```sql
-- Maps integer IDs to WhatsApp JID strings
jid._id -> integer PK
jid.user -> phone number or group ID prefix
jid.server -> "s.whatsapp.net" (individual), "g.us" (group), "broadcast"
jid.raw_string -> full JID
```

#### `chat` - Conversations
```sql
chat._id -> integer PK
chat.jid_row_id -> FK to jid._id
chat.subject -> group name (NULL for 1-on-1)
chat.archived -> archive status
chat.sort_timestamp -> last activity
```

#### `message` - Messages
```sql
message._id -> integer PK
message.chat_row_id -> FK to chat._id
message.from_me -> 0=incoming, 1=outgoing
message.key_id -> unique message identifier
message.sender_jid_row_id -> FK to jid._id
message.status -> delivery status code
message.timestamp -> Unix epoch milliseconds
message.message_type -> numeric type code
message.text_data -> message text
message.starred -> bookmark flag
```

#### `message_media` - Media attachments
```sql
message_media.message_row_id -> FK to message._id
message_media.file_path -> relative path to media file
message_media.mime_type -> MIME type
message_media.file_hash -> SHA-256 for file matching
message_media.media_name -> filename
message_media.file_size -> bytes
message_media.media_duration -> audio/video duration (seconds)
message_media.width, height -> image/video dimensions
message_media.media_caption -> caption text
message_media.message_url -> WhatsApp server download URL
```

#### `message_quoted` - Reply references
```sql
message_quoted.message_row_id -> FK to message._id (the reply)
message_quoted.sender_jid_row_id -> who sent the original
message_quoted.text_data -> text of quoted message
message_quoted.message_type -> type of quoted message
```

### Message Type Codes

| Code | Type |
|------|------|
| 0 | Text |
| 1 | Image |
| 2 | Audio / Voice note |
| 3 | Video |
| 4 | Contact card (vCard) |
| 5 | Location |
| 6 | System / Group event |
| 7 | Link with preview |
| 8-9 | Document |
| 10 | Missed voice call |
| 13 | Animated GIF |
| 14 | Deleted message |
| 15 | Sticker |
| 16 | Live location |

### Message Status Codes (outgoing)

| Code | Meaning | UI |
|------|---------|-----|
| 0 | Unsent | Clock |
| 4 | Received by server | Single grey tick |
| 5 | Delivered | Double grey ticks |
| 13 | Read | Double blue ticks |

### Contact Resolution

To get human-readable names, join across databases:
1. `message.sender_jid_row_id` -> `jid.raw_string`
2. Match JID against `wa_contacts.jid` in `wa.db` -> `display_name`

### Media File Storage

| Android Version | Path |
|----------------|------|
| Pre-Android 11 | `/storage/emulated/0/WhatsApp/Media/` |
| Android 11+ | `/storage/emulated/0/Android/media/com.whatsapp/WhatsApp/Media/` |

Directory structure:
```
WhatsApp/Media/
    WhatsApp Images/       (+ Sent/ subdirectory)
    WhatsApp Video/        (+ Sent/)
    WhatsApp Audio/        (+ Sent/)
    WhatsApp Voice Notes/  (organized by month: 201912/)
    WhatsApp Documents/    (+ Sent/)
    WhatsApp Stickers/
    WhatsApp Animated Gifs/
```

File naming: `IMG-YYYYMMDD-WA0000.jpg`, `VID-YYYYMMDD-WA0000.mp4`, etc.

**Matching DB to files**: Use `message_media.file_path` (relative path) and verify with `file_hash` (SHA-256).

---

## Part 2: Technology Stack Evaluation

### Database Options for Primary Storage + Search

#### Option A: SQLite with FTS5

| Criterion | Assessment |
|-----------|------------|
| Substring search | FTS5 trigram tokenizer (SQLite 3.48+) enables it, 14ms on 18M rows |
| Multilingual | unicode61 handles Cyrillic/Hebrew but **cannot combine with trigram** in same FTS table |
| Architecture issue | Need TWO separate FTS tables (one for word search, one for substring) |
| Merge/import | Basic `INSERT OR REPLACE`. Single-writer lock blocks during bulk import |
| Deployment | Zero config, single file |
| **Verdict** | **Too limited.** Two-FTS-table architecture is fragile. Single-writer blocks imports. |

#### Option B: PostgreSQL with pg_trgm + Full-Text Search

| Criterion | Assessment |
|-----------|------------|
| Substring search | pg_trgm provides true substring matching via GIN trigram indexes |
| Russian | Built-in `russian` text search config with stemming |
| Hebrew | No built-in config; needs PGroonga extension or custom dictionaries |
| Performance | pg_trgm has "recheck" overhead; slower than dedicated search for substring |
| Merge/import | Excellent: `MERGE` (v15+), `INSERT ON CONFLICT`, `COPY` for bulk. MVCC = no read blocks |
| Deployment | Requires running server; well-supported via Docker/managed services |
| **Verdict** | **Strong for storage and merge, but search needs help for substring across 3 languages** |

#### Option C: Elasticsearch / OpenSearch

| Criterion | Assessment |
|-----------|------------|
| Substring search | n-gram/edge-n-gram tokenizers, wildcard queries |
| Multilingual | Built-in Russian analyzer, **no built-in Hebrew** (needs plugin) |
| Performance | Purpose-built for search at massive scale |
| Merge/import | Bulk API; no relational dedup - requires app-level logic |
| Deployment | Heavy: JVM, 4-8GB RAM minimum, cluster management |
| **Verdict** | **Overkill.** Massive operational burden for a personal/small-team app. |

#### Option D: PostgreSQL + Typesense (Hybrid) -- RECOMMENDED

| Criterion | Assessment |
|-----------|------------|
| Substring search | **Typesense has explicit `infix: true` support** - the only lightweight engine with this |
| English | Excellent |
| Russian | Supported via `locale: "ru"` with ICU tokenization |
| Hebrew | Supported via `locale: "he"` with ICU tokenization |
| Performance | 28ms on 28M documents for prefix; infix is CPU-heavy but fine for short chat messages |
| Merge/import | PostgreSQL handles all merge/dedup; Typesense re-indexes after |
| Deployment | Typesense = single ~50MB binary; PostgreSQL in Docker |
| RAM | ~1-2GB for millions of messages in Typesense |
| **Verdict** | **Best fit. Clean separation: PostgreSQL owns data + merge, Typesense owns search.** |

### Web Framework Evaluation

#### SvelteKit -- RECOMMENDED

- **Smallest bundles**: Compiles to vanilla JS, 20-40KB vs Next.js ~70KB+
- **Built-in SSR**: Clean Google OAuth flow, server-side search queries
- **Simpler than React**: No re-rendering lifecycle issues for media players
- **Progressive enhancement**: Search works without JS
- **Form actions**: Built-in for search queries
- **Growing ecosystem**: Auth.js/Lucia support, good TypeScript integration

#### Why not Next.js?
App Router complexity (server/client component split) adds overhead without benefit for a focused search app. Better suited for large-team enterprise apps.

#### Why not Remix?
Solid second choice for form-heavy apps, but SvelteKit's compile-time approach produces smaller bundles and Svelte's reactivity is more intuitive for search-as-you-type.

---

## Part 3: Recommended Architecture

### Stack

```
┌─────────────────────────────────┐
│         SvelteKit App           │
│  (SSR + Client, Google OAuth)   │
├─────────────────────────────────┤
│         API Layer               │
│  (Server routes, auth guards)   │
├──────────┬──────────────────────┤
│          │                      │
│  PostgreSQL              Typesense        │
│  (Primary data store)    (Search index)   │
│  - All messages          - Infix search   │
│  - Contacts              - locale: en/ru/he│
│  - Media references      - Typo tolerance │
│  - User accounts         - Instant results│
│  - Merge/dedup logic     - Faceted search │
│          │                      │
├──────────┴──────────────────────┤
│         Media Storage           │
│  (Local filesystem or S3)       │
└─────────────────────────────────┘
```

### PostgreSQL Schema (our application DB)

Rather than keeping WhatsApp's raw SQLite structure, we should normalize into our own schema:

```sql
-- Conversations (chats)
CREATE TABLE conversations (
    id              BIGSERIAL PRIMARY KEY,
    wa_jid          TEXT UNIQUE NOT NULL,      -- original WhatsApp JID
    chat_type       TEXT NOT NULL,             -- 'individual', 'group', 'broadcast'
    display_name    TEXT,                      -- resolved contact name or group subject
    phone_number    TEXT,
    participant_count INTEGER,
    created_at      TIMESTAMPTZ,
    last_message_at TIMESTAMPTZ,
    avatar_path     TEXT,                      -- path to profile picture
    metadata        JSONB DEFAULT '{}'         -- flexible storage for extra data
);

-- Messages
CREATE TABLE messages (
    id              BIGSERIAL PRIMARY KEY,
    conversation_id BIGINT NOT NULL REFERENCES conversations(id),
    wa_key_id       TEXT NOT NULL,             -- original WhatsApp message key
    wa_message_id   BIGINT,                   -- original _id from msgstore.db
    sender_jid      TEXT,                      -- sender's WhatsApp JID
    sender_name     TEXT,                      -- resolved display name
    is_from_me      BOOLEAN NOT NULL DEFAULT FALSE,
    message_type    SMALLINT NOT NULL DEFAULT 0,
    text_content    TEXT,                      -- message body
    caption         TEXT,                      -- media caption
    status          SMALLINT DEFAULT 0,
    is_starred      BOOLEAN DEFAULT FALSE,
    is_forwarded    BOOLEAN DEFAULT FALSE,
    quoted_message_id BIGINT REFERENCES messages(id),
    quoted_text     TEXT,                      -- text of quoted message (denormalized)
    quoted_sender   TEXT,
    timestamp       TIMESTAMPTZ NOT NULL,
    received_at     TIMESTAMPTZ,
    read_at         TIMESTAMPTZ,
    metadata        JSONB DEFAULT '{}',
    import_batch_id TEXT,                      -- tracks which import this came from

    UNIQUE(wa_key_id, conversation_id)        -- dedup key for merging
);

-- Media attachments
CREATE TABLE media (
    id              BIGSERIAL PRIMARY KEY,
    message_id      BIGINT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    mime_type       TEXT,
    file_path       TEXT,                      -- path in our storage
    original_path   TEXT,                      -- original WhatsApp file path
    file_size       BIGINT,
    file_hash       TEXT,                      -- SHA-256 for dedup
    width           INTEGER,
    height          INTEGER,
    duration_seconds INTEGER,                  -- audio/video
    thumbnail_path  TEXT,                      -- generated thumbnail
    media_name      TEXT,
    metadata        JSONB DEFAULT '{}'
);

-- Contacts (from wa.db)
CREATE TABLE contacts (
    id              BIGSERIAL PRIMARY KEY,
    wa_jid          TEXT UNIQUE NOT NULL,
    phone_number    TEXT,
    display_name    TEXT,
    wa_name         TEXT,                      -- WhatsApp "push name"
    given_name      TEXT,
    family_name     TEXT,
    about           TEXT,                      -- status text
    avatar_path     TEXT,
    metadata        JSONB DEFAULT '{}'
);

-- Import tracking
CREATE TABLE imports (
    id              BIGSERIAL PRIMARY KEY,
    batch_id        TEXT UNIQUE NOT NULL,
    source_file     TEXT,
    schema_version  TEXT,                      -- 'old' or 'new'
    imported_at     TIMESTAMPTZ DEFAULT NOW(),
    message_count   INTEGER,
    conversation_count INTEGER,
    status          TEXT DEFAULT 'pending',    -- pending, running, completed, failed
    metadata        JSONB DEFAULT '{}'
);

-- Indexes
CREATE INDEX idx_messages_conversation ON messages(conversation_id, timestamp);
CREATE INDEX idx_messages_timestamp ON messages(timestamp);
CREATE INDEX idx_messages_sender ON messages(sender_jid);
CREATE INDEX idx_messages_type ON messages(message_type);
CREATE INDEX idx_messages_starred ON messages(is_starred) WHERE is_starred = TRUE;
CREATE INDEX idx_messages_wa_key ON messages(wa_key_id);
CREATE INDEX idx_media_message ON media(message_id);
CREATE INDEX idx_media_hash ON media(file_hash);
CREATE INDEX idx_contacts_jid ON contacts(wa_jid);

-- pg_trgm indexes as fallback for substring search
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX idx_messages_text_trgm ON messages USING GIN (text_content gin_trgm_ops);
```

### Typesense Collection Schema

```json
{
  "name": "messages",
  "fields": [
    {"name": "id", "type": "string"},
    {"name": "conversation_id", "type": "int64", "facet": true},
    {"name": "conversation_name", "type": "string", "facet": true},
    {"name": "sender_name", "type": "string", "facet": true},
    {"name": "text_content", "type": "string", "locale": "auto", "infix": true},
    {"name": "caption", "type": "string", "optional": true, "infix": true},
    {"name": "message_type", "type": "int32", "facet": true},
    {"name": "is_from_me", "type": "bool", "facet": true},
    {"name": "timestamp", "type": "int64"},
    {"name": "has_media", "type": "bool", "facet": true}
  ],
  "default_sorting_field": "timestamp"
}
```

### Import/Merge Workflow

```
1. User uploads new msgstore.db + wa.db + media folder
2. System detects schema version (check for 'message' vs 'messages' table)
3. Create import batch record in `imports` table
4. For old schema:
   - Read from `messages` + `chat_list` tables
   - Resolve JIDs inline from key_remote_jid
5. For new schema:
   - Read from `message` + `chat` + `jid` tables
   - Resolve JIDs via jid table joins
6. For each message:
   - INSERT INTO messages ... ON CONFLICT (wa_key_id, conversation_id) DO UPDATE
   - Only update if new data is richer (e.g., has status=read vs status=sent)
7. For media files:
   - Copy to organized storage: /media/{conversation_id}/{YYYY-MM}/{filename}
   - Deduplicate by file_hash
   - Generate thumbnails for images/videos
8. After merge completes:
   - Index new/changed messages into Typesense
   - Update conversation metadata (last_message_at, etc.)
```

### Authentication & Access Control

- **Google OAuth** via Auth.js (SvelteKit adapter)
- **Role-based access**:
  - `owner` - full access, can import databases, manage users
  - `viewer` - can search and browse, cannot import
- Store authorized users in a `users` table with their Google email

### Media Serving Strategy

- Store media files on local filesystem (or S3 for cloud deployment)
- Serve through authenticated API routes (not public URLs)
- Generate thumbnails on import:
  - Images: 200px wide JPEG thumbnails
  - Videos: Extract first frame as thumbnail using ffmpeg
  - Audio: Show waveform visualization or duration badge
  - Documents: Show icon based on file type + filename

### Deployment

**Single VPS (recommended for personal use)**:
- Docker Compose with 3 services: SvelteKit (Node.js), PostgreSQL, Typesense
- 4-8GB RAM VPS ($20-40/month)
- Nginx reverse proxy with HTTPS (Let's Encrypt)

```yaml
# docker-compose.yml (simplified)
services:
  app:
    build: .
    ports: ["3000:3000"]
    depends_on: [postgres, typesense]
    volumes:
      - ./media:/app/media
    environment:
      - DATABASE_URL=postgresql://user:pass@postgres:5432/whatsapp
      - TYPESENSE_URL=http://typesense:8108
      - GOOGLE_CLIENT_ID=...
      - GOOGLE_CLIENT_SECRET=...

  postgres:
    image: postgres:17
    volumes:
      - pgdata:/var/lib/postgresql/data
    environment:
      - POSTGRES_DB=whatsapp
      - POSTGRES_USER=user
      - POSTGRES_PASSWORD=pass

  typesense:
    image: typesense/typesense:27.1
    volumes:
      - tsdata:/data
    command: '--data-dir /data --api-key=xyz --enable-cors'

volumes:
  pgdata:
  tsdata:
```

---

## Part 4: Key Design Decisions Summary

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Primary DB | **PostgreSQL** | Best merge/dedup, MVCC concurrency, robust ecosystem |
| Search engine | **Typesense** | Only lightweight engine with native infix (substring) + multilingual locale support |
| Web framework | **SvelteKit** | Smallest bundles, great DX, built-in SSR, progressive enhancement |
| Keep original SQLite? | **No** - import into PostgreSQL | Unified schema handles both old/new WhatsApp schemas, better indexing, concurrent access |
| Media storage | **Filesystem** (organized) | Simple, fast, can migrate to S3 later |
| Auth | **Google OAuth** (Auth.js) | User's requirement, well-supported in SvelteKit |
| Deployment | **Docker Compose on VPS** | Simple, cost-effective, all-in-one |

---

## Part 5: Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Typesense infix search slow on long messages | Use `infix: "fallback"` mode; fall back to pg_trgm |
| WhatsApp schema changes in future dumps | Schema detection on import; versioned import adapters |
| 11 years of media = large storage | Lazy thumbnail generation; optional S3 migration |
| Hebrew RTL rendering issues | SvelteKit supports `dir="auto"`; CSS `direction` property per message |
| Merge conflicts (same message, different status) | Always keep the "most advanced" status (read > delivered > sent) |

---

## Next Steps

1. **Set up project scaffolding** - SvelteKit + Docker Compose + PostgreSQL + Typesense
2. **Build the importer** - Parse both old/new WhatsApp schemas, load into PostgreSQL
3. **Set up Typesense indexing** - Sync messages from PostgreSQL to Typesense
4. **Build the UI** - Conversation list, message view, search bars (global + per-conversation)
5. **Add authentication** - Google OAuth with role-based access
6. **Media handling** - Import, thumbnail generation, authenticated serving
7. **Merge workflow** - Upload new database dump, detect schema, merge/dedup

# AI Coding Agent Harnesses — TLS Stack Verification

Follow-up to the "Top 15 AI Coding Agent Harnesses" table. This pass tries to
convert every ⚙️ (inferred) or ⚠️ (unconfirmed) row into a ✅ by actually
obtaining the software and inspecting it — binary strings/symbols where a
compiled artifact was reachable, dependency-lock inspection where source was
reachable, and package contents where neither compiled binary nor lockfile
existed.

**Sandbox constraint:** this session's egress proxy allow-lists only
`registry.npmjs.org`, `pypi.org`, `index.crates.io` / `static.crates.io`,
`raw.githubusercontent.com`, and anonymous `git clone` of public GitHub repos.
Direct downloads from vendor CDNs (`downloads.cursor.com`,
`windsurf-stable.codeiumdata.com`, `app.warp.dev`, `github.com` release
assets, `codeload.github.com`) all returned `403` at the proxy. So closed-source
desktop apps (Cursor, Windsurf, Warp) could **not** be fetched here — those
rows are left as before, with the limitation noted explicitly rather than
guessed at.

## Newly confirmed

### 3. GitHub Copilot CLI — ✅ now confirmed
Fetched the real platform binary from npm (`@github/copilot-linux-x64`, the
package `@github/copilot` depends on per-OS/arch). `./copilot` is a 177 MB
stripped ELF, dynamically linked only against libc/libstdc++/libm/libpthread
(no libssl.so — TLS is statically embedded). `strings` shows it's a **Node.js
v24.18.1 Single Executable Application** (`sea-loader.js`, `node.js/v24.18.1`
build strings). It embeds:

```
OpenSSL 3.5.7 9 Jun 2026
```

No BoringSSL build marker anywhere; the `openssl_is_boringssl` strings present
are just Node's standard runtime feature-detection code (`process.features.openssl_is_boringssl`),
not evidence of BoringSSL — genuine BoringSSL Node builds don't ship both a
concrete `OpenSSL x.y.z` version banner and that check as dead code.

**TLS: OpenSSL 3.5.7**, statically linked into a Node.js 24 SEA binary.

### 4. Google Gemini CLI — ✅ confirmed (and simplified)
`npm view @google/gemini-cli` reports `deps: none` and the packed tarball
(449 files) contains **zero** `.node`/`.so`/`.dylib` binaries — it's pure
JS/TS with no native addons, executed by whatever Node.js runtime the user
has installed. There's no bundled OpenSSL/BoringSSL to pick between; it
simply inherits the host Node's TLS stack.

**TLS: OpenSSL, via the user's system Node.js runtime** (standard Node
distributions statically embed OpenSSL, not BoringSSL — that's Bun's/Deno's
choice, not Node's).

### 8. Cline — ✅ confirmed (extension-host runtime clarified)
Cloned `cline/cline`. `package.json` depends on `axios` (a wrapper over
Node's built-in `http`/`https` modules) for all network calls. Cline runs
entirely inside the **VS Code Extension Host**, which is a plain Node.js
process — *not* inside Chromium's renderer. So the Electron host's
BoringSSL-backed Chromium net stack is never in the path for Cline's own
traffic.

**TLS: OpenSSL**, via the Extension Host's Node.js runtime — the "BoringSSL
in Electron host" branch of the original guess does not apply to Cline's own
requests.

### 9. Amazon Q Developer CLI — ✅ confirmed
Cloned `aws/amazon-q-developer-cli` (Rust) and inspected `Cargo.lock`
directly — more reliable than binary strings since it pins exactly what got
built:

```
reqwest 0.12.24  → hyper-rustls 0.27.7 → rustls 0.23.33 → aws-lc-rs
```

`openssl-sys` and `native-tls` do not appear anywhere in the lockfile.

**TLS: rustls 0.23, with aws-lc-rs as the crypto provider** (not `ring`,
which is present only as a transitive dependency of the older `rustls 0.21`
pulled in by an unrelated sub-dependency).

### 11. Continue.dev — ✅ confirmed
Cloned `continuedev/continue`. Same picture as Cline for the VS Code
extension itself: `core/package.json` depends on `axios` and `node-fetch`
(both Node `https`-backed). Continue additionally ships a standalone
**`binary/`** component built with `pkg`, which bundles a prebuilt Node.js
runtime into a single executable — again a stock Node build, so still
OpenSSL, not BoringSSL.

**TLS: OpenSSL**, via Node.js (both the extension-host path and the `pkg`-
compiled binary component).

### 12. Warp — ✅ confirmed (analyzed locally, outside the sandbox)
This session's egress proxy couldn't reach `app.warp.dev`, so the user
downloaded the macOS build themselves and ran the same
binary-strings method locally against
`/Volumes/Warp/Warp.app/Contents/MacOS/stable`.

`otool`/`ldd`-equivalent shows **no dynamic TLS library** linked — the only
crypto-adjacent dynamic dependency is Apple's `Security.framework`, used for
the OS trust store/keychain, not the TLS protocol itself. The actual TLS
stack is statically compiled in, and embedded Cargo registry paths plus
error strings identify it precisely:

| Component | Version | Role |
|---|---|---|
| rustls | 0.23.39 | TLS 1.2/1.3 protocol engine |
| rustls-webpki | 0.103.13 | X.509 certificate path validation |
| aws-lc-rs | (via `crypto/aws_lc_rs`) | Cryptographic provider (default rustls backend) |
| hyper-rustls | 0.27.7 | rustls ↔ hyper HTTP client glue |
| tokio-rustls / async-tungstenite | 0.28.2 | async TLS + WebSocket transport |

Notable details:
- Crypto backend is **aws-lc-rs**, not `ring` — strings like `EVP_DigestFinal
  failed` / `digest update failed` are aws-lc-rs's BoringSSL-derived FIPS-
  oriented C core; the `ring` paths present are just rustls's internal module
  layout, not the active provider.
- No OpenSSL, BoringSSL-standalone, GnuTLS, NSS, or native-tls anywhere.
- Modern feature set compiled in: TLS 1.3, Encrypted Client Hello (ECH),
  GREASE, CRL checking, and post-quantum signature schemes (ML-DSA-44/65/87).
- Also links the AWS SDK's rustls provider (`aws-smithy-http-client`),
  consistent with Warp's cloud/AI backend calls.

**TLS: rustls 0.23 with the aws-lc-rs crypto provider**, statically linked;
`Security.framework` is OS-level trust/keychain integration only, not the
TLS implementation.

## Unchanged — could not obtain the artifact in this sandbox

- **Cursor / Windsurf** — closed-source Electron desktop apps; their
  download CDNs (`downloads.cursor.com`, `windsurf-stable.codeiumdata.com`)
  are not on this session's egress allow-list (`403` at the proxy). Original
  ⚙️ inferred rows stand.
- **Replit Agent** — server-side only; there is no client binary to fetch.
- **Devin** — cloud VM only; "Devin Local" is not publicly downloadable.

If a wider egress allow-list (or a machine with unrestricted internet) is
available, the same method — `file`/`ldd`/`strings` for the ELF/PE/Mach-O,
grepping for `OpenSSL <version>`, `BoringSSL`, `rustls`, symbol names like
`rustls_*`/`aws_lc_*`/`SSL_library_init` — would settle Cursor and Windsurf
the same way it settled Copilot CLI and Warp.

## Updated table (deltas only)

| # | Harness | TLS | Confidence |
|---|---|---|---|
| 3 | GitHub Copilot CLI | OpenSSL 3.5.7 (Node.js 24 SEA binary) | ✅ confirmed (binary strings) |
| 4 | Google Gemini CLI | OpenSSL (host Node.js runtime; pure JS, no native deps) | ✅ confirmed (package contents) |
| 8 | Cline | OpenSSL (Node.js Extension Host, via axios) | ✅ confirmed (source) |
| 9 | Amazon Q Developer CLI | rustls 0.23 + aws-lc-rs | ✅ confirmed (Cargo.lock) |
| 11 | Continue.dev | OpenSSL (Node.js, extension host + `pkg` binary) | ✅ confirmed (source) |
| 12 | Warp | rustls 0.23 + aws-lc-rs | ✅ confirmed (binary strings, analyzed locally) |
| 5 | Cursor | BoringSSL (Chromium)/OpenSSL (Node) | ⚙️ unchanged — binary unreachable |
| 6 | Windsurf | BoringSSL (Chromium)/OpenSSL (Node) | ⚙️ unchanged — binary unreachable |
| 14 | Replit Agent | OpenSSL (Python default) | ⚙️ unchanged — no client binary exists |
| 15 | Devin | not documented | ⚠️ unchanged — no local binary exists |

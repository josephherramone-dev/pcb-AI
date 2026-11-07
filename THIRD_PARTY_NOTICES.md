# Third-party notices

This project uses the following third-party software, data and services. Their
licenses apply to those components, not to the rest of this repository.

## KiCad EDA — GPL-3.0-or-later

- What: `kicad-cli` and KiCad's Python module (`pcbnew`) generate, check and export
  the native KiCad projects.
- How it is used: KiCad runs as a **separate program**. The backend starts it as a
  subprocess (or in the official `kicad/kicad` container), passes files and
  command-line arguments, and reads back files and reports. KiCad source code is not
  copied into this repository.
- The three scripts in `backend/app/kicad/scripts/` are executed *inside* KiCad's
  Python interpreter and `import pcbnew`. See `docs/legal/LEGAL.md` (§1) for the
  licensing recommendation for those files.
- Source code: https://gitlab.com/kicad/code/kicad (the KiCad 9.0.9 and 7.0.11
  releases were used during development).

## KiCad symbol and footprint libraries — CC-BY-SA-4.0 with design exception

- Copyright: KiCad Community.
- License: Creative Commons Attribution-ShareAlike 4.0 International, with this
  exception (verbatim from the license shipped with the libraries):

  > To the extent that the creation of electronic designs that use 'Licensed
  > Material' can be considered to be 'Adapted Material', then the copyright holder
  > waives article 3 of the license with respect to these designs and any generated
  > files which use data provided as part of the 'Licensed Material'.

- Effect for users: designs and generated files (schematics, boards, Gerbers, BOMs)
  that use the libraries are **not** subject to the ShareAlike requirement.
- Effect for this platform: the backend reads the libraries and shows symbol and
  footprint graphics in the browser. That is sharing the library data itself, so the
  attribution and license notice are shown in the app ("Legal & notices") and written
  into every exported project (`NOTICE.txt`).
- The libraries are not stored in this repository; they come from the installed KiCad
  or the `kicad/kicad` image.
- Library sources: https://kicad.github.io/symbols/ and https://kicad.github.io/footprints/

## Claude by Anthropic — Anthropic Commercial Terms of Service

- What: the optional AI design assistant calls the Anthropic Messages API with the
  official `anthropic` Python SDK (MIT license), using an API key held only by the
  backend.
- Terms: use of the API is governed by Anthropic's Commercial Terms of Service and
  Usage Policy, which the operator of the deployment accepts when creating the API key.
  See https://www.anthropic.com/legal.

## Open-source dependencies

All runtime dependencies are listed with their declared licenses in
[`docs/legal/DEPENDENCY_LICENSES.md`](docs/legal/DEPENDENCY_LICENSES.md), generated
by `scripts/third_party_licenses.py` (49 Python packages, 86 npm production packages
at the time of writing).

Summary: almost all are permissive (MIT, BSD, Apache-2.0, ISC). The exceptions are
weak-copyleft libraries that are used unmodified, as separate libraries:

| Package | License | Notes |
|---|---|---|
| psycopg, psycopg-binary | LGPL-3.0-only | PostgreSQL driver, used unmodified as a replaceable Python package. |
| certifi | MPL-2.0 | CA bundle, used unmodified. |
| @img/sharp-libvips-* / @img/sharp-wasm32 | LGPL-3.0-or-later (+ Apache-2.0, MIT) | Pulled in by Next.js for image optimisation, prebuilt shared library, unmodified. |

There are no GPL or AGPL packages among the runtime dependencies.

## Container base images

- `kicad/kicad:9.0` (KiCad, Debian 12 and their components; mostly GPL/LGPL).
- `postgres:16-alpine`, `redis:7-alpine`, `node:22.22.0-bookworm-slim`.

Distributing built images means distributing these components; see
`docs/legal/LEGAL.md` (§2).

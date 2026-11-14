# Procedure JSON Schema (v2, item 4.2)

Used by `POST /api/procedimentos/importar-json/preview`, `POST /api/procedimentos/importar-json`,
and the export endpoints `GET /api/procedimentos/{id}/exportar-json` and
`GET /api/procedimentos/exportar-json?ids=...`. Field names match the existing `Procedimento`
model/API (`ProcedimentoListItem`/`ProcedimentoDetail`) so export → re-import is a direct
round-trip, with no name mapping required.

The import body is a single object or an array of objects — both endpoints accept either and
normalize internally.

## JSON Schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "Procedure",
  "type": "object",
  "required": ["titulo", "html_original"],
  "properties": {
    "id": {
      "type": ["string", "null"],
      "format": "uuid",
      "description": "Only meaningful on import, to match an existing procedure for the duplicate/overwrite flow. Omit when creating a new one -- a fresh id is always assigned by the server."
    },
    "titulo": { "type": "string", "minLength": 1, "maxLength": 255 },
    "titulo_en": {
      "type": ["string", "null"],
      "maxLength": 255,
      "description": "English title fallback. On create, if omitted, it is filled automatically by the same eager HTML->English translation the manual upload already does."
    },
    "tags": { "type": "array", "items": { "type": "string" }, "default": [] },
    "categorias": {
      "type": "array",
      "items": { "type": "string" },
      "default": [],
      "description": "Fixed taxonomy codes from api/app/categorias.py / web/src/categorias.ts (VIRT, K8S, STR, SEC, OBS, OS, EDGE, IA). Unknown codes are dropped silently, same as the manual-upload form."
    },
    "cliente_origem": { "type": ["string", "null"], "maxLength": 255 },
    "data_origem": { "type": ["string", "null"], "format": "date" },
    "status": { "type": "string", "enum": ["rascunho", "validado"], "default": "rascunho" },
    "versao": { "type": "integer", "minimum": 1, "default": 1 },
    "html_original": {
      "type": "string",
      "minLength": 1,
      "description": "The procedure body. Same h2/h3-per-section convention as every other procedure in the base (see CLAUDE.md) -- sections are always re-derived from this on import, never carried over as a separate field."
    },
    "idioma_original": {
      "type": ["string", "null"],
      "maxLength": 5,
      "description": "\"pt\"|\"en\"|\"es\", if known. Detected automatically on import/first view otherwise."
    }
  }
}
```

## Fields intentionally NOT in this schema

- `origem_conhecimento`, `gerado_por_ia`, `criado_por_id`, `responsavel_id`, `created_at` — set by
  the server on import (`origem_conhecimento="manual"`, `gerado_por_ia=false`, owner = whoever
  imports), never taken from the file.
- Chunks/embeddings (`procedimento_chunks`) — always re-derived from `html_original` on import or
  overwrite, exactly like the manual HTML upload and the cross-instance sync feature already do.
  Never exported or imported as data of their own.
- `traducoes` (the per-language HTML translation cache) — reset on import/overwrite; the first
  view in a non-original language regenerates it lazily, same as any other procedure.

## Import flow

1. `POST /api/procedimentos/importar-json/preview` with the raw JSON (object or array) returns,
   per item: `valido` (bool), `erros` (field-level messages, never fails the whole request for one
   bad item), and `duplicado_id`/`duplicado_titulo` if an existing procedure matches — by `id` when
   given, otherwise by `titulo` + overlapping `categorias` (the closest proxy to "título+produto"
   this model has, since `Procedimento` has no single "product" field).
2. The caller decides, per duplicate: skip (default) or overwrite.
3. `POST /api/procedimentos/importar-json` with `{"itens": [...], "sobrescrever_ids": ["<uuid>", ...]}`
   actually imports. A duplicate not listed in `sobrescrever_ids` is skipped (`status: "pulado"`); one
   that is gets updated in place (same `id`, so `Classificacao`/`Anexo`/`RfiItem` links pointing at it
   never break) instead of becoming a second row. New items are created via the same
   `_criar_procedimento` path the manual upload and cross-instance sync already use.

## Export

- `GET /api/procedimentos/{id}/exportar-json` — one procedure, same shape as the import schema
  above (including its real `id`, for a future re-import/overwrite round-trip).
- `GET /api/procedimentos/exportar-json?ids=<uuid>,<uuid>,...` — several at once, as a JSON array;
  omit `ids` to export every procedure.

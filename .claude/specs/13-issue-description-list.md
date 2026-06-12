# Spec: Issue Description in Open Issues List

## Overview

The Open Issues list on the repository detail page currently shows only the issue number and title.
This feature surfaces the issue body (description) as a second line below the title, truncated to two
lines, so users can immediately understand the context of an issue without opening it.

This reduces friction in the "Select an issue → Start a run" workflow: operators can evaluate whether
an issue is a good candidate for Forge without navigating away from the repository view.

---

## Depends On

- Repository ingestion (issues are already fetched and stored with their `body` field).

---

## User Story

"As a developer reviewing issues for Forge to tackle, I want to see a brief description of each issue
in the list so that I can decide which issue to assign without opening each one individually."

---

## Agent Changes

No agent changes.

---

## Workflow Changes

No workflow changes.

---

## Database Changes

No database changes. The `body` column already exists on the `issues` table
(`apps/api/app/models/issue.py:27`).

---

## Retrieval Changes

No retrieval changes.

---

## API Changes

### Modify — `IssueOut` schema

**File:** `apps/api/app/schemas/repository.py`

Add `body` field to the existing `IssueOut` Pydantic model:

```python
class IssueOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    number: int
    title: str
    body: str | None        # ← add this
    state: str
    labels: list[str]
```

No new endpoints. The existing `GET /repositories/{id}/issues` endpoint already returns `IssueOut`
objects; adding the field propagates automatically.

**Request schema:** unchanged.

**Response schema (diff):**
```json
{
  "total": 2,
  "issues": [
    {
      "id": "...",
      "number": 6,
      "title": "Resolving Grammar Error",
      "body": "The word 'recieve' on line 12 of index.html should be 'receive'.",  // ← new
      "state": "open",
      "labels": []
    }
  ]
}
```

---

## Frontend Changes

### `apps/web/src/lib/api.ts`

Add `body` to the `IssueOut` TypeScript interface:

```ts
export interface IssueOut {
  id: string
  number: number
  title: string
  body: string | null      // ← add this
  state: string
  labels: string[]
}
```

### `apps/web/src/components/repositories/issues-list.tsx`

Render `issue.body` as a second line below the title.

Design rules (matching existing dark design):
- Font: `text-xs` / `text-neutral-500` (or `text-gray-400` to match current palette)
- Clamp to 2 lines: `line-clamp-2`
- Only render if `issue.body` is non-null and non-empty
- No additional spacing — keep the compact row height

```tsx
<div className="min-w-0 flex-1">
  <p className="truncate text-sm text-gray-800">{issue.title}</p>
  {issue.body && (
    <p className="mt-0.5 text-xs text-gray-400 line-clamp-2 leading-relaxed">
      {issue.body}
    </p>
  )}
  {/* labels and errors unchanged */}
</div>
```

---

## Files To Modify

| File | Change |
|---|---|
| `apps/api/app/schemas/repository.py` | Add `body: str \| None` to `IssueOut` |
| `apps/web/src/lib/api.ts` | Add `body: string \| null` to `IssueOut` interface |
| `apps/web/src/components/repositories/issues-list.tsx` | Render `issue.body` below title |

---

## Files To Create

None.

---

## New Packages

None.

---

## Implementation Rules

- TypeScript strict mode — `body: string | null`, not `any`
- No business logic in API routes — the schema change is in `schemas/`, not in the router
- Targeted edits only — touch only the three files listed above
- Maintain existing architecture — no new components, no state management changes

---

## Definition Of Done

- [ ] `IssueOut` Pydantic schema includes `body: str | None`
- [ ] `GET /repositories/{id}/issues` response includes `body` for each issue
- [ ] Frontend `IssueOut` TypeScript interface includes `body: string | null`
- [ ] Issue body renders as a second line below the title in `issues-list.tsx`
- [ ] Body is clamped to 2 lines (`line-clamp-2`) — no overflow
- [ ] Issues with no body (`null` or empty) show only the title (no empty space)
- [ ] Labels and Tackle button are unaffected
- [ ] TypeScript compiles with no errors

---

## Architecture Impact

- **Affected systems:** backend schema, frontend API client, one UI component
- **Dependencies introduced:** none
- **Scalability concerns:** none — `body` is already fetched from DB; no extra query
- **Future extensions:** body could be used for issue embedding search or as context
  passed to the IssueAnalyzerAgent in future phases

---

## Risks

| Risk | Mitigation |
|---|---|
| Very long issue bodies break layout | `line-clamp-2` enforces a hard 2-line cap |
| `body` is null for older ingested issues | Guard with `{issue.body && ...}` |
| API consumers relying on exact `IssueOut` shape break | `body` is additive (nullable); existing consumers ignore unknown fields |
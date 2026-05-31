# Herd Health & Breeding Management

**Date**: 2026-05-30
**Status**: Approved
**Next ticket**: 0003

---

## Problem

Flock & Fiber tracks the wool pipeline (animals → clips → mill → inventory → sales) but has no record of animal health events or breeding activity. Operators must track medications, vet visits, and pregnancies externally. As a farm grows this causes missed vaccinations, forgotten vet costs, and no forward view of incoming offspring.

---

## Scope

Two coupled features delivered as one ticket:

1. **Health event tracking** — reactive log of vet visits, medications, vaccinations per animal
2. **Breeding management** — pairing records, pregnancy tracking, birth recording with optional offspring creation

Out of scope: medication withdrawal period alerts, heat/cycle tracking, farm contacts directory (separate ticket), market pricing.

---

## Architecture

### Data model — Python (`src/`)

#### `src/health.py`

```python
class HealthCategory(str, Enum):
    VET_VISIT = "vet_visit"
    MEDICATION = "medication"
    VACCINATION = "vaccination"
    OTHER = "other"

@dataclass
class HealthEvent:
    animal_id: str
    category: HealthCategory
    event_date: date
    description: str              # required human-readable summary
    id: str = field(default_factory=lambda: str(uuid4()))
    drug_name: str | None = None  # medication
    dose: str | None = None       # medication
    end_date: date | None = None  # medication course end
    next_due_date: date | None = None  # vaccination follow-up
    cost_usd: float | None = None
    notes: str = ""

    def to_dict(self) -> dict[str, Any]: ...
    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> HealthEvent: ...

class HealthLedger:
    def add(self, event: HealthEvent) -> None: ...          # raises ValueError on duplicate id
    def get(self, event_id: str) -> HealthEvent: ...        # raises KeyError on unknown
    def remove(self, event_id: str) -> None: ...            # for corrections
    def list_for_animal(self, animal_id: str) -> list[HealthEvent]: ...  # sorted by event_date desc
    def list_all(self) -> list[HealthEvent]: ...
    def upcoming_due(self, as_of: date, horizon_days: int = 30) -> list[HealthEvent]: ...
    # Returns events where next_due_date is within horizon_days of as_of
```

#### `src/breeding.py`

```python
GESTATION_DAYS: dict[str, int] = {
    "sheep": 147,
    "alpaca": 335,
    "goat": 150,
}

def expected_due_date(species: str, breeding_date: date) -> date | None:
    # Returns breeding_date + gestation days for known species, else None

class BreedingStatus(str, Enum):
    BRED = "bred"
    CONFIRMED_PREGNANT = "confirmed_pregnant"
    DELIVERED = "delivered"
    FAILED = "failed"

VALID_BREEDING_TRANSITIONS: dict[BreedingStatus, set[BreedingStatus]] = {
    BreedingStatus.BRED: {BreedingStatus.CONFIRMED_PREGNANT, BreedingStatus.FAILED},
    BreedingStatus.CONFIRMED_PREGNANT: {BreedingStatus.DELIVERED, BreedingStatus.FAILED},
}
# DELIVERED and FAILED are terminal — no further transitions

@dataclass
class BirthRecord:
    breeding_record_id: str
    dam_id: str
    birth_date: date
    liveborn_count: int
    id: str = field(default_factory=lambda: str(uuid4()))
    stillborn_count: int = 0
    offspring_ids: list[str] = field(default_factory=list)  # Animal IDs created for offspring
    notes: str = ""

    def to_dict(self) -> dict[str, Any]: ...
    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> BirthRecord: ...

@dataclass
class BreedingRecord:
    dam_id: str          # mother (Animal in our registry)
    breeding_date: date
    id: str = field(default_factory=lambda: str(uuid4()))
    sire_id: str | None = None   # sire in our registry (optional)
    sire_name: str = ""           # free-text for external sires
    status: BreedingStatus = BreedingStatus.BRED
    expected_due_date: date | None = None  # computed at creation from species
    birth: BirthRecord | None = None       # populated on delivery
    notes: str = ""

    def to_dict(self) -> dict[str, Any]: ...
    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> BreedingRecord: ...

class BreedingLedger:
    def add(self, record: BreedingRecord) -> None: ...       # raises ValueError on duplicate id
    def get(self, record_id: str) -> BreedingRecord: ...     # raises KeyError on unknown
    def list_for_animal(self, animal_id: str) -> list[BreedingRecord]: ...  # where dam_id matches
    def list_active_pregnancies(self) -> list[BreedingRecord]: ...
    # Returns records with status bred or confirmed_pregnant, sorted by expected_due_date asc
    def transition(self, record_id: str, new_status: BreedingStatus) -> None: ...
    # Raises ValueError on invalid transition
    def deliver(self, record_id: str, birth: BirthRecord) -> None: ...
    # Transitions to DELIVERED and embeds BirthRecord; raises ValueError if already delivered
```

### Persistence — `flock.py`

Four new `FarmStore` methods following the `load_preorders` / `save_preorders` pattern:

```python
FarmStore.load_health_events() -> HealthLedger    # reads "health_events" key, default []
FarmStore.save_health_events(ledger: HealthLedger) -> None
FarmStore.load_breeding_records() -> BreedingLedger   # reads "breeding_records" key, default []
FarmStore.save_breeding_records(ledger: BreedingLedger) -> None
```

Serialization delegates entirely to `HealthEvent.to_dict/from_dict` and `BreedingRecord.to_dict/from_dict`.

---

## API surface — Rust

Two new route files registered in `mod.rs` and `main.rs`.

### `api/src/routes/health.rs`

| Method | Path | Response | Notes |
|--------|------|----------|-------|
| GET | `/api/animals/:id/health-events` | `200 Vec<HealthEvent>` sorted by `event_date` desc | `404` if animal unknown |
| POST | `/api/animals/:id/health-events` | `201 HealthEvent` | `404` if animal unknown; `422` if `description` empty or `event_date` invalid |
| DELETE | `/api/animals/:id/health-events/:eid` | `204` | `404` if either id unknown |

### `api/src/routes/breeding.rs`

| Method | Path | Response | Notes |
|--------|------|----------|-------|
| GET | `/api/breeding-records` | `200 Vec<BreedingRecord>` | optional `?status=active_pregnancies` filter |
| GET | `/api/animals/:id/breeding-records` | `200 Vec<BreedingRecord>` | where `dam_id = :id`; `404` if animal unknown |
| POST | `/api/breeding-records` | `201 BreedingRecord` | `422` if `dam_id` unknown, `breeding_date` invalid, or `sire_id` provided but unknown |
| PATCH | `/api/breeding-records/:id/status` | `200 BreedingRecord` | body: `{"status": "confirmed_pregnant" \| "failed"}`; `422` on invalid transition with `{"error": "Cannot transition from X to Y"}`; `404` unknown id |
| POST | `/api/breeding-records/:id/birth` | `201 BreedingRecord` (with embedded birth) | body: `{birth_date, liveborn_count, stillborn_count?, create_offspring?, notes?}`; `422` if already delivered or `liveborn_count < 1`; `404` unknown id; if `create_offspring: true`, generates `liveborn_count` new Animal records (inheriting `species` and `breed` from dam; `name` set to `"<dam_name> offspring <N>"`, `notes` set to `"Born <birth_date>, dam: <dam_name>"`; no dob stored — operator updates later) and populates `offspring_ids` |

### `api/src/models.rs` additions

```rust
// HealthEvent, HealthCategory enums
// BreedingRecord, BreedingStatus, BirthRecord structs
// FarmData gains:
//   #[serde(default)] health_events: Vec<HealthEvent>
//   #[serde(default)] breeding_records: Vec<BreedingRecord>
```

---

## UI — Svelte

### Navigation change

`Animals` nav item renamed to `Herd` (🐑). Nav becomes: Herd | Mill Orders | Inventory | Sync | Booth.

### `web/src/routes/Herd.svelte` (replaces Animals.svelte)

**Dashboard layout:**

```
┌─────────────────────────────────────────────────────┐
│ 🐣 Pregnancies              │ 🩺 Health alerts       │
│  Clover — due Jun 15        │  Woolly — vaccine due  │
│  Daisy — due Jul 3          │  Luna — vet Jun 12     │
│  + Record breeding          │  + Log health event    │
└─────────────────────────────────────────────────────┘
│ All Animals                                          │
│  🐑 Clover  shearing due  Merino sheep               │
│  🐑 Daisy   ✓ current     BFL sheep                  │
│  🦙 Luna    unknown        Huacaya alpaca             │
│  + Add animal                                        │
└─────────────────────────────────────────────────────┘
```

- Alert strips are hidden when empty (no active pregnancies / no upcoming health events within 30 days)
- Clicking an animal row opens AnimalDetail
- "+ Record breeding" opens a slide-in form (dam selector, sire name/id, breeding date)
- "+ Log health event" opens a slide-in form (animal selector, category, description, type-specific fields)

### `web/src/routes/AnimalDetail.svelte` (extracted from Animals.svelte)

Current clip-history detail view extracted into its own component. Gains two new tabs:

- **Health** — chronological list of health events; inline "+ Add" button opens form
- **Breeding** — list of breeding records for this animal as dam; status badges; "+ Record breeding" button

### `web/src/lib/api.ts` additions

```typescript
export interface HealthEvent { id, animal_id, category, event_date, description,
  drug_name, dose, end_date, next_due_date, cost_usd, notes }

export interface BreedingRecord { id, dam_id, sire_id, sire_name, breeding_date,
  status, expected_due_date, birth: BirthRecord | null, notes }

export interface BirthRecord { id, breeding_record_id, dam_id, birth_date,
  liveborn_count, stillborn_count, offspring_ids, notes }

// Typed API functions for each endpoint
```

---

## Testing

- **Python** (`tests/test_health.py`, `tests/test_breeding.py`): HealthLedger add/list/remove; BreedingLedger state machine (invalid transitions raise ValueError); `expected_due_date` by species; `deliver()` embeds BirthRecord; `list_active_pregnancies()` filters correctly
- **Rust** (inline `#[cfg(test)]` in each route file): tower oneshot integration tests; 404 on unknown animal/record; 422 on invalid status transition; 422 on recording birth for already-delivered record; `create_offspring: true` creates correct number of Animal records
- **Svelte**: `npm run check` (svelte-check) + `tsc --noEmit`

---

## Implementation order

1. **Python** — `src/health.py`, `src/breeding.py`, `flock.py` store methods, pytest suites
2. **Rust** — models, `health.rs`, `breeding.rs`, register in `mod.rs` + `main.rs`
3. **TypeScript** — `api.ts` additions, `offline.ts` (no queue changes needed — health/breeding are online-only for now)
4. **Svelte** — `Herd.svelte` (extracts and replaces Animals.svelte), `AnimalDetail.svelte`, Nav update

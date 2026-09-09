# What the Server / Voice Agent Actually Knows

This is a reference dump of every fact the backend or the LLM (Kimi/Groq, on a
phone call or in the Ask Agent test box) can draw on — pulled directly from the
live database on 2026-09-09 (updated same day after Buffing, Exterior
Detailing, and Shampooing were added), not retyped from memory. If the
catalog changes, regenerate this rather than hand-editing it.

There are **two separate knowledge sources**, and they answer two separate
kinds of question:

1. **The booking catalog** (`services`, `service_prices`, `add_ons`,
   `add_on_prices` tables) — the source of truth for what a booking actually
   costs. `list_services` / `list_addons` (Vapi tools) and the admin API read
   from here. This is never guessed or improvised.
2. **The uploaded RAG document** (`shinepro-pricing (1).md`, indexed for the
   `ask` tool / Ask Agent) — used for freeform Q&A ("how much is X", "do you
   serve Texas") when a caller isn't actively booking. It's a separate file an
   admin uploaded, and the numbers on it should match the catalog above — see
   **Known discrepancies** at the bottom for the two places they've drifted.

---

## 1. Services (from the booking catalog — what's actually charged)

Prices vary by vehicle category. A service with no row for a category isn't
offered for that vehicle at all — the voice agent is told to say so and
suggest an alternative rather than guessing a price.

### Interior & Exterior Detailing — 120 min (convenience bundle)
Interior and Exterior are also independently bookable as their own services
(see **Interior Detailing Only** below and **Exterior Detailing** further
down) — this bundle exists for a caller who wants both together at the
bundle price rather than booking them as two separate line items.
| Category | Price |
|---|---|
| Sedan | $200 |
| SUV | $220 |
| Truck | $220 |
| Coupe | $200 |
| Van | $400 |
| Mini Van | $300 |
| Hatchback | $200 (priced like a sedan) |

### Interior Detailing Only — 90 min
Has a **price floor** — the minimum this can be discounted down to when a
customer insists.
| Category | Price | Floor |
|---|---|---|
| Sedan | $150 | $150 (no room — already at floor) |
| SUV | $180 | $170 |
| Truck | $170 | $170 (no room) |
| Coupe | $160 | $160 (no room) |
| Van | $250 | $250 (no room) |
| Mini Van | $200 | $200 (no room) |
| Hatchback | $150 | $150 (no room) |

### Buffing & Waxing — 150 min (convenience bundle)
| Category | Price |
|---|---|
| Sedan | $200 |
| SUV | $200 |
| Truck | $200 |
| Coupe | $200 |
| Van | $300 |
| Mini Van | $200 |
| Hatchback | $200 |

### Buffing — 120 min (standalone, no waxing)
Independently bookable as its own service — same price as the Buffing &
Waxing bundle above for each category (no separate standalone number was
ever given, so it mirrors the bundle). Add the **Waxing Only** add-on
(section 2) on top if the caller wants both but doesn't want the bundle.
Same price table as Buffing & Waxing above.

### Exterior Detailing — 90 min (standalone, no interior)
Independently bookable, priced identically to **Interior Detailing Only**
below for each category (mirrored per the shop's instruction — no separate
exterior-only number exists). Includes a wax step as part of the detail.
| Category | Price | Floor |
|---|---|---|
| Sedan | $150 | $150 (no room) |
| SUV | $180 | $170 |
| Truck | $170 | $170 (no room) |
| Coupe | $160 | $160 (no room) |
| Van | $250 | $250 (no room) |
| Mini Van | $200 | $200 (no room) |
| Hatchback | $150 | $150 (no room) |

### Paint Correction — 390 min (5–8 hours, all three levels)
| Level | Sedan/SUV/Truck/Coupe/Mini Van/Hatchback | Van |
|---|---|---|
| Level 1 (minor swirls) | $400 | $500 |
| Level 2 (moderate scratches, multi-stage polish) | $1,000 | $1,000 |
| Level 3 (deep scratches, 3-stage correction, showroom finish) | $1,500 | $1,500 |

### Ceramic Coating — 150 min — **Sedan / SUV / Truck only**, not offered for coupe, van, minivan
| Tier | Price |
|---|---|
| 2 Year | $400 |
| 3 Year | $800 |
| 5 Year | $1,200 |

### Motorcycle Full Detailing — 90 min
$170 flat. Motorcycles are a fully bookable, real category — not rejected.

### Boat Detailing — 120 min, and Trailer Detailing — 90 min
**$35 per foot**, not a category lookup — the agent must ask the caller for
the length in feet (`vehicle_length_ft`) before it can quote or book.

---

## 2. Add-ons (from the booking catalog)

Small extras stacked on top of a base service. Most are flat-priced
regardless of vehicle; **Waxing Only and Shampooing are the exceptions** and
vary by category like a service does. Buffing, Interior Detailing, Exterior
Detailing, Ceramic Coating, and Paint Correction are NOT add-ons — they're
full services (section 1), independently bookable in their own right.

| Add-on | Duration | Price | Floor |
|---|---|---|---|
| Pet Hair Removal | 45 min | $70 | none |
| Headlight Restoration | 45 min | $100 | none |
| Headliner Cleaning | 45 min | $50 | none |
| Engine Bay Cleaning | 30 min | $70 | none |
| **Waxing Only** — Sedan/SUV/Truck/Coupe/Hatchback | 30 min | $70 | **$50** |
| **Waxing Only** — Van/Mini Van | 30 min | $100 | **$50** |
| **Shampooing** — Sedan/SUV/Truck/Mini Van/Coupe/Hatchback | 45 min | $50 | none |
| **Shampooing** — Van | 45 min | $120 | none |

Waxing Only's $50 floor is **insist-only** — it's never the default quote,
only what a customer can be discounted down to if they push back on price.
Shampooing has no stated floor.

---

## 3. Discount / negotiation policy

If a caller says a price is too expensive:
- Offer **$10 off the total package price** — never off one individual line
  item inside it.
- If they still object, offer another $10, and this can repeat.
- The backend clamps every discount request server-side to the **combined
  floor** of every item in the booking (base service + any extra services +
  any add-ons) — the agent never has to calculate the floor itself, it just
  keeps offering $10 increments and reads back whatever `price_cents` the
  backend actually returns.
- Never offered proactively — only in response to the caller objecting.

---

## 4. Vehicle categories the classifier recognizes

Keyword match first (instant, free); an LLM call (Kimi, falling back to Groq)
only fires when nothing in the list below matches.

- **Standard** (priced per the tables above): `sedan`, `suv`, `truck`,
  `coupe`, `van`, `minivan`, `hatchback` (priced as sedan)
- **Special**: `motorcycle` — its own flat-priced service
- **Length-based**: `boat`, `trailer` — priced per foot, needs a length
- Recognizes dozens of real makes/models per category (F-150, Silverado,
  Tacoma → truck; CR-V, RAV4, Wrangler → suv; Corolla, Camry, Civic → sedan;
  Sienna, Odyssey → minivan; Sprinter, Transit → van; Mustang, Camaro →
  coupe; Ninja, Harley, Vespa → motorcycle; pontoon, yacht, bass boat →
  boat), plus hyphenated model names (F-150, CR-V) handled correctly.

---

## 5. Booking rules

- **Hours**: 8:00 AM – 6:00 PM, **in the customer's own local time** (real
  per-state timezone lookup, not server UTC) — 7 days a week.
- **Booking window**: up to 60 days ahead; nothing in the past.
- **Service area**: fully mobile, all US states.
- Vehicle access and a parking space needed; the crew brings their own water
  and power.

---

## 6. The RAG document, verbatim (what `ask` / Ask Agent is grounded in)

Re-ingested on 2026-09-09 to add Buffing, Exterior Detailing, and Shampooing
(previously missing entirely — see prior discrepancy notes below), fix Waxing
Only's per-category pricing, and add Trailer Detailing. This is the exact
text of the `shinepro-pricing (1).md` document now indexed:

> # ShinePro Detailing - Pricing Menu
>
> ## Standard Vehicles
>
> ### SUV
> | Service | Price |
> |---|---|
> | Interior & Exterior Detailing | $220 |
> | Interior Detailing Only | $180 |
> | Exterior Detailing Only | $180 |
> | Buffing & Waxing | $200 |
> | Buffing Only (no wax) | $200 |
> | Paint Correction Level 1 | $400 |
> | Paint Correction Level 2 | $1,000 |
> | Paint Correction Level 3 | $1,500 |
>
> ### Sedan
> | Service | Price |
> |---|---|
> | Interior & Exterior Detailing | $200 |
> | Interior Detailing Only | $170 |
> | Exterior Detailing Only | $150 |
> | Buffing & Waxing | $200 |
> | Buffing Only (no wax) | $200 |
> | Paint Correction Level 1 | $400 |
> | Paint Correction Level 2 | $1,000 |
> | Paint Correction Level 3 | $1,500 |
>
> ### Truck
> | Service | Price |
> |---|---|
> | Interior & Exterior Detailing | $220 |
> | Interior Detailing Only | $170 |
> | Exterior Detailing Only | $170 |
> | Buffing & Waxing | $200 |
> | Buffing Only (no wax) | $200 |
> | Paint Correction Level 1 | $400 |
> | Paint Correction Level 2 | $1,000 |
> | Paint Correction Level 3 | $1,500 |
>
> ### Coupe
> | Service | Price |
> |---|---|
> | Interior & Exterior Detailing | $200 |
> | Interior Detailing Only | $180 |
> | Exterior Detailing Only | $160 |
> | Buffing & Waxing | $200 |
> | Buffing Only (no wax) | $200 |
> | Paint Correction Level 1 | $400 |
> | Paint Correction Level 2 | $1,000 |
> | Paint Correction Level 3 | $1,500 |
>
> ## Larger Vehicles
>
> ### Van
> | Service | Price |
> |---|---|
> | Interior & Exterior Detailing | $400 |
> | Interior Detailing Only | $250 |
> | Exterior Detailing Only | $250 |
> | Buffing & Waxing | $300 |
> | Buffing Only (no wax) | $300 |
> | Paint Correction Level 1 | $500 |
> | Paint Correction Level 2 | $1,000 |
> | Paint Correction Level 3 | $1,500 |
>
> ### Mini Van
> | Service | Price |
> |---|---|
> | Interior & Exterior Detailing | $300 |
> | Interior Detailing Only | $200 |
> | Exterior Detailing Only | $200 |
> | Buffing & Waxing | $200 |
> | Buffing Only (no wax) | $200 |
> | Paint Correction Level 1 | $400 |
> | Paint Correction Level 2 | $1,000 |
> | Paint Correction Level 3 | $1,500 |
>
> ## Motorcycle
> | Service | Price |
> |---|---|
> | Full Detailing | $170 |
>
> ## À La Carte Add-Ons (stack on top of any service above)
> | Add-on | Price |
> |---|---|
> | Pet Hair Removal | $70 |
> | Headlight Restoration | $100 |
> | Headliner Cleaning | $50 |
> | Engine Bay Cleaning | $70 |
>
> ### Waxing Only (add-on, no buffing) — varies by vehicle
> | Vehicle | Price |
> |---|---|
> | Sedan | $70 |
> | SUV | $70 |
> | Truck | $70 |
> | Coupe | $70 |
> | Van | $100 |
> | Mini Van | $100 |
>
> ### Shampooing (add-on, carpet/upholstery) — varies by vehicle
> | Vehicle | Price |
> |---|---|
> | Sedan | $50 |
> | SUV | $50 |
> | Truck | $50 |
> | Coupe | $50 |
> | Mini Van | $50 |
> | Van | $120 |
>
> ## Premium Add-Ons
>
> ### Ceramic Coating
> *Available for: Sedan, SUV, Truck*
> | Duration | Price |
> |---|---|
> | 2 Year Protection | $400 |
> | 3 Year Protection | $800 |
> | 5 Year Protection | $1,200 |
>
> ### Boat Detailing
> **$35 per foot**
>
> ### Trailer Detailing
> **$35 per foot**
>
> ## Service Descriptions
>
> ### Interior Detailing
> Includes:
> - Thorough vacuuming of seats, carpets, floor mats, and trunk area
> - Complete wipe-down of all interior surfaces including dashboard, door
>   panels, center console, and trims
> - All plastic components carefully dressed to restore a clean, refined finish
> - Interior windows cleaned for clear visibility
> - Cabin finished with long-lasting air freshener
>
> ### Exterior Detailing
> Includes:
> - Foam-based hand wash followed by pressure rinse to safely remove dirt and
>   contaminants
> - Wheels, tires, and rims cleaned, degreased, and dressed for a fresh
>   appearance
> - Door jambs and trunk seals carefully cleaned
> - Vehicle dried using microfiber towels to prevent scratches and water spots
> - A wax step is included as part of the exterior detail
>
> ### Buffing
> Machine buffing of the paint to remove light swirl marks and restore gloss.
> Sold on its own (no wax step) or bundled with waxing as "Buffing & Waxing."
>
> ### Waxing Only
> A protective wax coat applied on its own, without a buffing step. Sold
> separately from Buffing & Waxing.
>
> ### Shampooing
> Deep shampoo and extraction cleaning of carpets and upholstery, for stains
> and odors beyond a standard vacuum.
>
> *Contact ShinePro Detailing for custom packages and fleet discounts!*

---

## Known discrepancies (RAG document vs. real booking catalog)

All four discrepancies previously listed here (Waxing Only's flat $70 not
reflecting the $100 van/minivan price, missing Trailer Detailing, missing
price floors, and missing Buffing/Exterior Detailing/Shampooing entirely)
were fixed by re-ingesting the updated document above on 2026-09-09.
Live-verified: "exterior detailing of suv" → $180, "buffing for a sedan" →
$200, "waxing of sedan" → $70, "shampooing for a van" → $120, "trailer
detailing" → $35/ft — all grounded, all matching the booking catalog.

One thing still not in the RAG document: **price floors** (e.g. Interior
Detailing Only's $150–250 floors, Waxing Only's $50 floor, Buffing's implied
$200 floor via the bundle). This only matters for the negotiation flow,
which `book_appointment` already enforces correctly server-side regardless
of what `ask` says — a caller asking generally "what's your cheapest
interior detail" just won't hear about the floor concept from `ask`.

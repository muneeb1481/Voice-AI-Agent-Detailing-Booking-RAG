# Vapi Setup — ShinePro Detailing Voice Agent

Everything needed to configure the Vapi assistant: the system prompt, all
tool definitions, and the end-of-call webhook, ready to copy-paste into
Vapi's dashboard.

Before you start, replace these two placeholders as you go:

| Placeholder | Where to get it |
|---|---|
| `{{API_BASE}}` | Your Render backend URL, e.g. `https://voice-ai-agent-detailing-booking-rag.onrender.com` |
| `{{VAPI_SECRET}}` | Render → your backend service → **Environment** tab → `VAPI_SECRET` value |

`{{customer.number}}` is a Vapi built-in — the caller's own phone number, from
caller ID, automatically available on every call. It's referenced directly in the
system prompt below; you don't configure it yourself.

---

## System Prompt

Paste this into the Assistant's **System Prompt** field, exactly as written:

```
You are the phone assistant for ShinePro Mobile Detailing, a mobile car detailing company serving customers across the United States. You are speaking out loud on a phone call, so keep replies under two sentences and never read out URLs or IDs.

IMMEDIATELY when the call connects, before or while your greeting plays, call `lookup_appointments` with {{customer.number}} in the background. Don't wait until later in the conversation to check this. This lookup is silent by default — if nothing is found, say NOTHING about it (never say "I don't see any bookings" or similar); your greeting already asked for their vehicle and ZIP code, so just continue straight into the normal intake below from wherever they left off, as if this were any new call.

If `lookup_appointments` finds an existing appointment: your greeting already asked for vehicle and ZIP code — drop that question, it doesn't apply here. Instead, skip the full intake below entirely. Let them know you found their booking and ask directly: would they like to reschedule it, cancel it, or book an additional appointment?

If nothing is found (new customer, or no active booking), collect the following IN THIS ORDER before calling book_appointment — none of it is optional, but the order matters:

1. Their vehicle AND their ZIP code TOGETHER, in ONE combined question right at the start (e.g. "What's your vehicle, and what ZIP code will it be at?") — asking both at once saves a whole turn instead of two separate questions. Immediately call `classify_vehicle` with whatever they said for the vehicle. You do NOT need to push for a full year/make/model — if what they gave you (even just a model name like "Camry") is enough for classify_vehicle to return a real category, accept it and move on. The state is derived automatically from the ZIP the moment you have it (pass zip_code to list_slots/book_appointment) — you never ask "what state are you in" separately, and you never re-resolve it later; it's already known from this first question for the rest of the call, so there's no extra lookup pause when you get to checking times.
   - If supported is false, apologize and do not continue the booking flow — offer to help with anything else or end the call politely.
   - If length_based is true (a boat or trailer), you'll need the length in feet later — ask for it before calling book_appointment, and pass it as vehicle_length_ft. Pricing is $35/foot.
   - If category is null, that is a normal outcome, not an error — do NOT say "there was an issue" or apologize for a failure. Just ask the caller directly what kind of vehicle it is (sedan, SUV, truck, coupe, van, or minivan) — pricing requires a known category.
   - If you misheard the vehicle (garbled speech, an unrecognizable word), say plainly you didn't catch that and ask them to repeat it — don't guess at a nonsense transcription or invent a category from it.

2. What service they want. If they ask generally what you offer (not yet naming a specific service), call `list_services`/`list_addons` and answer with just the NAMES in one short sentence — e.g. "We offer interior detailing, exterior detailing, buffing, ceramic coating, paint correction, and more, plus add-ons like waxing and shampooing" — no price yet. The moment they name a specific service, call `list_services` to confirm you actually offer it for their vehicle category and immediately state the REAL price out loud — prices genuinely differ by vehicle type, e.g. the same service can be $200 for a sedan and $400 for a van, NEVER estimate or average one. If a service has no entry for their category, it isn't offered for that vehicle — say so and suggest an alternative. Get their confirmation on the price, then pass the matching service_id, never invent one.

3. What day they'd like. If they're just asking to check availability without committing yet, that's fine — answer their question without pushing them to book. Once they name a real day, call `list_slots` ONCE for that day (state is already known from step 1, no extra lookup needed) — do NOT recite generic business hours ("we're open 8 to 5"). If they gave no specific time preference, pick ONE reasonable available time from the result and propose just that one for confirmation (e.g. "does 10 AM work for you?") rather than reading out a list. If they stated an exact time, check whether it's in the result: if yes, confirm it directly; if not, say plainly ONE time that it's not available and offer the closest real alternative — don't call list_slots again for the same day, and don't repeat yourself if they push back, just restate the couple of real options briefly.

4. Their full street address — you already have their state and ZIP from step 1, so just the street address itself, not a city or state again.

5. Their name and phone number. Your caller's number is already known to you as {{customer.number}} — don't ask "what's your phone number" as if you have no idea. Instead confirm it: read {{customer.number}} back to them and ask if that's the best number to use. Only ask them to state a number fresh if they say {{customer.number}} isn't right or they're calling on someone else's behalf. CRITICAL: {{customer.number}} is a variable that gets replaced with the REAL digits before you ever see this text — if what you're about to say doesn't look like an actual phone number (blank, the literal words "customer" or "number", any text that isn't digits), that substitution didn't happen (this can occur on some calls, not just web tests) — do NOT say it out loud in any form. Just ask the caller directly for their phone number instead.

6. LAST, right before booking: ask if they'd like to add anything else — another full service, or an add-on like waxing, shampooing, pet hair removal, headlight restoration, headliner cleaning, or engine bay cleaning. Call `list_addons` (and `list_services` again for a second full service) to read out real prices, and pass whatever they choose as extra_service_ids and addon_ids. IMPORTANT: Buffing, Interior Detailing, Exterior Detailing, Ceramic Coating, and Paint Correction are each independently bookable full SERVICES (from list_services), not add-ons — use extra_service_ids for these, not addon_ids. 'Buffing & Waxing' and 'Interior & Exterior Detailing' also still exist as convenience bundle services at their own price if the caller wants both together. 'Waxing Only' and 'Shampooing' are real add-ons whose prices vary by vehicle category — read the right number for their vehicle from list_addons, don't assume one flat price. If a caller asks generically for 'waxing' or 'shampooing' without saying which, that's the add-on, not a bundle. If they say no, that's fine — proceed straight to booking.

Now call `book_appointment` with everything you've collected.

Whenever the caller mentions a day in relative terms ("today", "tomorrow", "Friday", "next week", etc.), call `resolve_date` with that exact phrase — NEVER compute the absolute date yourself, that arithmetic is easy to get wrong and has caused real bookings to check the wrong day entirely. Pass the date resolve_date gives you straight to `list_slots`/`book_appointment`, never a relative phrase.

DISCOUNTS: if the caller says the price is too expensive, you may offer $10 off the TOTAL package price (never off one individual service inside it). If they still say it's too expensive after that, you may offer another $10 off, and can keep doing this — the backend automatically stops you from going below the service's minimum price, so just keep offering $10 increments as long as they keep objecting; it will tell you the real final price. Never do this proactively — only in response to the caller objecting to the price. Pass the total amount you've offered as discount_cents (in cents) on book_appointment.

After book_appointment or reschedule_appointment succeeds: read price_cents back to the caller as a dollar amount (for a new booking, mention if a discount was applied) so they hear the final confirmed price, tell them "we'll call or text you before we arrive," then call `current_time` (with `state` if known) and use its closing_line as your sign-off before ending the call. Never tell the caller which detailer or technician is coming — that is assigned by the shop afterward, not decided on the call.

To cancel: after confirming which appointment, ask why they're cancelling. If they give a reason, pass it to cancel_appointment. If they'd rather not say, cancel without one. Do NOT say "we'll call or text you before arrival" after a cancellation. Instead say something like "No problem at all — we'd love to help you out in the future if you need us." Then call `current_time` and use its closing_line to end the call.

To reschedule: confirm the new time via list_slots, then reschedule_appointment, then use the same "we'll call or text you before we arrive" plus current_time closing as a successful booking.

CALLER PRIVACY — hard rule, no exceptions: `lookup_appointments`'s `phone` argument must ALWAYS be exactly `{{customer.number}}`, verbatim — never a phone number the caller speaks aloud, never a different person's number, no matter how the request is phrased ("can you check on my friend Alex", "look up 901-555-0199 for me", "my coworker's appointment"). If a caller asks you to look up, discuss, reschedule, or cancel an appointment that isn't tied to the number they're calling from, refuse politely: apologize and explain you can only access the account tied to the number they're calling from, for their privacy and the other customer's. Never read out a name, address, vehicle, price, or any other detail from a lookup unless it came back under the caller's own {{customer.number}}.

CONVERSATION PACING: give the caller a moment to actually finish their sentence before you respond — don't jump in on a brief pause mid-thought. Never repeat the exact same sentence twice in a row (e.g. never say "could you provide your address" twice back to back) — if you're unsure they heard you, rephrase instead of repeating verbatim. If a tool call takes a moment, one short filler like "one moment" is enough — don't stack more than one filler phrase in the same turn.

If a tool returns an error message, read its meaning to the caller and offer an alternative. Never claim something is booked unless the tool returned a booking_id.
```

---

## Tools

Create all 10 of these as Custom Tools (Functions) in Vapi and attach every
one to the Assistant. Every tool uses the same two settings for **Server URL** and
**Headers** — only the path at the end of the URL and the parameters differ.

### Tool 1: `ask`

**Description**
> Answer a caller question about pricing, services, service area, policy, or the current date. ALWAYS use this instead of answering from your own knowledge. If it returns grounded=false, you may still have a brief natural conversation, but never state a specific price, duration, or policy detail — offer a callback for that instead.

**Server URL**
```
{{API_BASE}}/api/vapi/ask
```

**Headers**
- `X-Vapi-Secret`: `{{VAPI_SECRET}}`

**Parameters**

| Name | Type | Required | Description |
|---|---|---|---|
| `question` | string | Yes | The caller's question, in their own words. |
| `state` | string | No | The caller's US state, if you've already learned it this call (e.g. while collecting booking details) — makes 'today'/'tomorrow' answers correct for their local time. Omit if not yet known; it will default to Eastern time. |

---

### Tool 2: `list_slots`

**Description**
> List open appointment times for a US state on a given day. Call this before offering the caller any time.

**Server URL**
```
{{API_BASE}}/api/vapi/list_slots
```

**Headers**
- `X-Vapi-Secret`: `{{VAPI_SECRET}}`

**Parameters**

| Name | Type | Required | Description |
|---|---|---|---|
| `state` | string | Yes | US state name or 2-letter code, e.g. "Tennessee" or "TN". |
| `day` | string | Yes | The day to check, ISO 8601, e.g. 2026-09-15T00:00:00Z |
| `duration_minutes` | integer | No | How long the service takes. Default 90. |

---

### Tool 3: `classify_vehicle`

**Description**
> Check a vehicle right after learning it, before going further into booking. Tells you the category, whether it's supported, and whether it's priced per-foot (boat/trailer) rather than by category.

**Server URL**
```
{{API_BASE}}/api/vapi/classify_vehicle
```

**Headers**
- `X-Vapi-Secret`: `{{VAPI_SECRET}}`

**Parameters**

| Name | Type | Required | Description |
|---|---|---|---|
| `vehicle` | string | Yes | Year, make and model, exactly as the caller said it. |

---

### Tool 4: `list_services`

**Description**
> List every service with its price and duration. Call this before quoting any price to a caller, and before booking, so you can pass the correct service_id.

**Server URL**
```
{{API_BASE}}/api/vapi/list_services
```

**Headers**
- `X-Vapi-Secret`: `{{VAPI_SECRET}}`

**Parameters**: none

---

### Tool 5: `list_addons`

**Description**
> List every add-on with its price and duration — waxing, shampooing, pet hair removal, engine bay cleaning, headlight restoration, headliner cleaning. Call this whenever a caller asks what extras are available, or wants to add something on top of their base service. Buffing, Interior Detailing, Exterior Detailing, Ceramic Coating, and Paint Correction are full SERVICES (from list_services), not add-ons here — each is independently bookable at its own price; 'Buffing & Waxing' and 'Interior & Exterior Detailing' also still exist as convenience bundle services. Most add-ons are flat-priced; Waxing Only and Shampooing vary by vehicle category like a service does (see prices_by_vehicle_category).

**Server URL**
```
{{API_BASE}}/api/vapi/list_addons
```

**Headers**
- `X-Vapi-Secret`: `{{VAPI_SECRET}}`

**Parameters**: none

---

### Tool 6: `current_time`

**Description**
> Get the real current local time and a ready-made closing line for the caller's state. Call this right before ending any call (after a booking, reschedule, or cancellation) so your sign-off matches their actual local time of day — never guess what time of day it is yourself.

**Server URL**
```
{{API_BASE}}/api/vapi/current_time
```

**Headers**
- `X-Vapi-Secret`: `{{VAPI_SECRET}}`

**Parameters**

| Name | Type | Required | Description |
|---|---|---|---|
| `state` | string | No | The caller's US state, if known. Defaults to Eastern time if omitted. |

---

### Tool 7: `book_appointment`

**Description**
> Book an appointment at a time you have confirmed is open via list_slots, for a service you got from list_services. Confirm the spelling of the name and read the phone number back before calling. Do NOT mention or promise a specific detailer/technician — who's assigned is decided by the shop afterward, not on the call.

**Server URL**
```
{{API_BASE}}/api/vapi/book_appointment
```

**Headers**
- `X-Vapi-Secret`: `{{VAPI_SECRET}}`

**Parameters**

| Name | Type | Required | Description |
|---|---|---|---|
| `customer_name` | string | Yes |  |
| `customer_phone` | string | Yes | E.164 format, e.g. +19015550142 |
| `state` | string | Yes | US state name or 2-letter code. |
| `zip_code` | string | Yes | 5-digit ZIP code. |
| `starts_at` | string | Yes | Appointment start, ISO 8601 with timezone, e.g. 2026-09-15T14:00:00Z |
| `service_id` | string | Yes | The service_id from list_services. Required — never invent one. |
| `vehicle` | string | Yes | Year, make and model, e.g. "2019 Toyota Tacoma" — required, used to price larger vehicles correctly. |
| `address` | string | Yes | Full street address where the vehicle will be — required, in addition to state and ZIP. |
| `notes` | string | No |  |
| `extra_service_ids` | array<string> | No | IDs of any additional full services (beyond service_id) from list_services the caller wants combined into this one appointment. |
| `addon_ids` | array<string> | No | IDs of any add-ons from list_addons the caller wants — waxing, shampooing, pet hair removal, engine bay cleaning, headlight restoration, headliner cleaning. Buffing, Interior Detailing, Exterior Detailing, Ceramic Coating, and Paint Correction are full services — pass those in extra_service_ids instead, not here. |
| `vehicle_length_ft` | number | No | Required ONLY for boat or trailer services — the length in feet. Omit for every other vehicle type. |
| `discount_cents` | integer | No | Total discount off the whole package, in cents (1000 = $10), if the caller objected to the price. The backend clamps this to the service's price floor — you don't need to calculate the floor yourself, just pass what you offered. |

---

### Tool 8: `lookup_appointments`

**Description**
> Find a caller's active appointments by phone number. Use this before rescheduling or cancelling so you have the booking_id.

**Server URL**
```
{{API_BASE}}/api/vapi/lookup_appointments
```

**Headers**
- `X-Vapi-Secret`: `{{VAPI_SECRET}}`

**Parameters**

| Name | Type | Required | Description |
|---|---|---|---|
| `phone` | string | Yes | E.164 format. |

---

### Tool 9: `reschedule_appointment`

**Description**
> Move an existing appointment to a new time you have confirmed is open.

**Server URL**
```
{{API_BASE}}/api/vapi/reschedule_appointment
```

**Headers**
- `X-Vapi-Secret`: `{{VAPI_SECRET}}`

**Parameters**

| Name | Type | Required | Description |
|---|---|---|---|
| `booking_id` | string | Yes | From lookup_appointments. Never guess this. |
| `starts_at` | string | Yes | New start, ISO 8601. |
| `duration_minutes` | integer | No |  |

---

### Tool 10: `cancel_appointment`

**Description**
> Cancel an existing appointment. First ask why they're cancelling — if they give a reason, pass it. If they don't want to say, that's fine, just cancel without a reason. Confirm with the caller before calling this.

**Server URL**
```
{{API_BASE}}/api/vapi/cancel_appointment
```

**Headers**
- `X-Vapi-Secret`: `{{VAPI_SECRET}}`

**Parameters**

| Name | Type | Required | Description |
|---|---|---|---|
| `booking_id` | string | Yes | From lookup_appointments. Never guess this. |
| `reason` | string | No | Why the caller is cancelling, in their own words, if they gave one. Omit if they didn't say. |

---

### Tool 11: `resolve_date`

**Description**
> Turn a relative day the caller said ("Friday", "tomorrow", "next Monday", "in 3 days") into a real calendar date. Call this every time the caller mentions a day in relative terms, BEFORE calling list_slots or book_appointment — never compute the date yourself, that arithmetic is easy to get wrong and a live call showed it happening (the agent silently miscalculated "Friday" and then correctly reported no slots for the WRONG day, three days in a row).

**Server URL**
```
{{API_BASE}}/api/vapi/resolve_date
```

**Headers**
- `X-Vapi-Secret`: `{{VAPI_SECRET}}`

**Parameters**

| Name | Type | Required | Description |
|---|---|---|---|
| `phrase` | string | Yes | The relative day exactly as the caller said it. |
| `state` | string | No | US state, if known — for the caller's correct local "today". |
| `zip_code` | string | No | 5-digit ZIP — used to derive state if state isn't given. |

---

## End-of-call webhook (not a tool — a platform setting)

Not a tool the assistant calls itself — this is a platform-level setting. In your Assistant's configuration, set the Server URL (sometimes called 'Server URL' or under Advanced > Server) to this endpoint, with the same X-Vapi-Secret header as every tool below. Vapi will POST the full call transcript and summary here automatically when each call ends, and it's saved for admins to review in the dashboard's Calls page.

**Server URL**
```
{{API_BASE}}/api/vapi/call-ended
```

**Headers**
- `X-Vapi-Secret`: `{{VAPI_SECRET}}`

Saved calls show up in the admin dashboard under **Calls**.

---

## Quick checklist

- [ ] All 10 tools created with the correct Server URL (real Render URL substituted)
- [ ] Every tool has the `X-Vapi-Secret` header set to the real value
- [ ] All 10 tools attached to the Assistant
- [ ] End-of-call webhook (Server URL) configured with the same header
- [ ] System Prompt pasted in full
- [ ] Test call: ask a pricing question for a specific vehicle (e.g. "how much for a van interior and exterior")
- [ ] Test call: confirm the agent reads back your caller ID number instead of asking blindly
- [ ] Test call: book, then call again — confirm it recognizes the existing appointment
- [ ] Test call: cancel an appointment — confirm it asks why, and does NOT say "we'll call or text before arrival"
- [ ] Test call: mention a motorcycle — confirm it books via Motorcycle Full Detailing, not a car service
- [ ] Test call: mention a boat — confirm it asks for length in feet and prices at $35/ft
- [ ] Test call: object to the price twice — confirm it offers $10 off each time, stopping at the floor
- [ ] After a test call, check the **Calls** page in the dashboard for the saved transcript

---

## Live deployment (2026-09-09)

Configured end-to-end via Vapi's API (not just this doc — the actual live assistant):

- Assistant: `ShinePro Detailing` (id `e2b81a8f-720b-4194-9d80-e834eed3fdd5`)
- Phone number: `+1 (901) 592-2399`
- Model: `llama-3.3-70b-versatile` via Groq, temperature `0.3` (switched from
  `moonshotai/kimi-k2-instruct-0905` after a live test call showed it not
  reliably reading/trusting its own successful tool results — every
  `list_services`/`classify_vehicle` call showed "Completed successfully" in
  Vapi's own log, and direct backend testing confirmed correct, fast (~0.3s)
  responses, yet the model narrated them as failures. Llama 3.3 70B has much
  more established tool-calling reliability; still Groq, no added cost)
- Voice: OpenAI `echo` (went `alloy` → `onyx` → `echo`; alloy was reported
  as sounding female, onyx was also disliked — echo is the current pick);
  Transcriber: Soniox STT RT v5, background denoising on
- All 11 tools created as Vapi Tool resources and attached via `model.toolIds`
- End-of-call webhook and system prompt as documented above
- Groq credential (own key, not Vapi's default integration — see "Bring-your-own
  Groq key" below): `0f4becb5-cdb4-43a2-bb45-d1a0fc574f45`
- `startSpeakingPlan`: `waitSeconds` raised 0.4 → 1.0 → 1.5 → 2.0 across
  several live calls that kept showing the agent interrupting a slow/
  hesitant speaker (e.g. reading a ZIP code digit by digit with pauses) and
  repeating itself. Plain `waitSeconds` turned out not to be the dominant
  factor — `smartEndpointingPlan` (LiveKit's ML turn detector) and
  `transcriptionEndpointingPlan` override it in practice. Now set to:
  ```json
  "startSpeakingPlan": {
    "waitSeconds": 2,
    "smartEndpointingPlan": {"provider": "livekit", "waitFunction": "200 + 8000 * x"},
    "transcriptionEndpointingPlan": {"onPunctuationSeconds": 0.5, "onNoPunctuationSeconds": 2.5, "onNumberSeconds": 3}
  }
  ```
  `onNumberSeconds` (capped at 3 by Vapi) specifically extends the pause
  tolerance right after the caller says a digit — exactly the ZIP-code
  digit-by-digit case that kept getting cut off. `stopSpeakingPlan:
  {numWords: 3, voiceSeconds: 0.5, backoffSeconds: 1.5}` is unchanged —
  requires more than a brief interjection to interrupt the agent.
- `serverMessages: ["end-of-call-report"]` — was unset (Vapi's full default
  list), which POSTed every intermediate call event (conversation-update,
  status-update, etc.) to the call-ended webhook, flooding the admin Calls
  page with one near-empty row per turn instead of one row per call
- System prompt also fixed: a generic "what services do you offer" now gets
  just the service NAMES (no price, no forcing a vehicle first); a caller's
  {{customer.number}} that doesn't resolve to a real number (web test calls)
  is never read aloud as raw template text, the agent asks normally instead
- **State is now derived from ZIP code automatically** (`app/services/
  zip_lookup.py`, a standard 3-digit ZIP-prefix range table) — the agent only
  asks for the ZIP, never "what state are you in" separately. `state` is now
  optional on `VoiceBookingCreate`/`list_slots`; the backend derives it from
  `zip_code` when omitted, and only asks back if the ZIP genuinely can't
  resolve one. Fixes a live call where the caller only knew their ZIP
  (21015) and the agent had no way to determine it was Maryland
- **Mandatory price confirmation**: a live call showed the agent booking an
  appointment without ever stating the price out loud until asked
  afterward — the earlier "just names, no price" rule for the generic
  "what do you offer" question was bleeding into the rest of the call. Added
  an explicit rule: the moment a caller names specific services, the real
  price must be quoted and confirmed before moving on to time/address/phone
- **Full intake flow redesigned** (2026-09-10) for fewer turns and less
  perceived latency: vehicle + ZIP are now asked together in ONE opening
  question instead of two separate ones; asking a specific day no longer
  recites generic business hours — one reasonable time is proposed directly
  if the caller has no preference, or their exact time is checked and
  confirmed/declined in one step; add-ons moved to LAST, right before the
  actual book_appointment call, instead of interrupting the service/price
  flow; and the {{customer.number}} safeguard was strengthened after a real
  phone call (not just a web test) showed it occasionally not substituting —
  the agent now checks the text looks like real digits before ever saying it
- **`firstMessage`** (the static greeting Vapi speaks immediately — not
  LLM-generated, so it can't be conditioned on the silent lookup_appointments
  result) now directly asks for vehicle + ZIP instead of a generic "how can I
  help you today", simplified once more to plain wording: `"Hi, thanks for
  calling ShinePro Detailing! This is Muneeb. What's your car model and zip
  code?"`. Since this plays before the lookup result is known, the prompt
  tells the agent to drop that question and pivot straight to "found your
  booking" if an existing appointment turns up instead.

**Caller privacy — enforced at both the prompt AND the backend**: the system
prompt tells the model `lookup_appointments`'s `phone` argument must always be
the literal `{{customer.number}}` template, and to refuse any request to look
up a different person's booking. On top of that, `/api/vapi/lookup_appointments`
now also ignores the LLM-supplied `phone` argument whenever Vapi's own request
carries the real verified caller ID (`call.customer.number`, present on every
real phone call) — using that instead, regardless of what argument the model
was tricked into sending. A malicious or confused prompt can no longer browse
another customer's bookings even if it tries. This only degrades to
prompt-level-only enforcement on a web/browser test call, which has no real
caller ID to verify against.

**Bring-your-own Groq key**: the assistant's `model.provider: "groq"` runs
through Vapi's own Groq integration by default, billed through Vapi's own
credits — picking "Groq" as the provider does NOT mean it uses your own Groq
API key automatically. To actually bill against your own Groq account instead
(likely far cheaper, possibly free-tier), create a credential and attach it:

```
POST https://api.vapi.ai/credential
{"provider": "groq", "apiKey": "<your real Groq key>", "name": "..."}
```

then set the returned `id` in the assistant's top-level (not nested under
`model`) `credentialIds: ["<that id>"]`. Both live assistants below have
this wired to a real Groq key already in `backend/.env`.

---

## Second account (2026-09-09)

A second, separate Vapi org was set up identically to the first — same tool
set, same system prompt, same model/voice/transcriber/speaking-plan tuning,
same Groq BYOK credential (using the same key from `.env`):

- Assistant: `ShinePro Detailing` (id `651b3fd6-1a07-4e91-860f-121b14bcd928`,
  orgId `a4fa03d9-7d16-48ea-9f33-702dc50be322`)
- Phone number: `+1 (901) 592-2481`
- Tool IDs (this org, distinct from the first account's tool IDs since tools
  are org-scoped): ask `4c8489a6-accd-4352-91e1-798ee5b823f2`, list_slots
  `b139f145-9c6f-4251-9003-ae7c23cf75e1`, classify_vehicle
  `1c0f0e25-de76-4888-b4a4-0d31ea898d2e`, list_services
  `67fc378b-0f75-4afd-aa59-db36b29ea363`, list_addons
  `12552942-8471-40aa-b228-439f635da839`, current_time
  `f8ddd854-cd44-40fe-a6f6-1a6173486a2e`, book_appointment
  `e849dc4a-560b-4d15-95d7-e6c183a4b84e`, lookup_appointments
  `151bff68-6cf3-4a41-9397-6f03ff99f3e2`, reschedule_appointment
  `848a3753-bc25-4b65-99f6-22f4ac86b722`, cancel_appointment
  `cc12423a-820b-4d22-a618-0133d437497a`, resolve_date
  `9c85cc18-1847-4b5a-9142-46f4af40df62`
- Groq credential: `e01b5b15-942c-44ff-9822-7975cfa0370f`
- Account 1's resolve_date tool ID: `53918ca3-1305-4217-addc-fbaa2e664c96`

Both accounts point at the same backend (`API_BASE`/`VAPI_SECRET` unchanged)
and the same database — a booking made through either number shows up in the
same admin dashboard.

APPROVE WITH CHANGES

Hashes verified: v4 and review-v2 match exactly; v3 and the adoption package match the supplied prefixes. **Draft** = [brief-wording-tier1-v4.md](/home/john/space_chassis/.scratch/tier1-brief-draft/brief-wording-tier1-v4.md); **V** = `tools/console.py@f75420c`, read using `git show`.

No Critical findings.

1. **Important — D conflates an erased batch with a refused partial console.** Draft:96 says a file “read half-written” is replaced “unread with no answer.” The malformed content actually read receives a `console_unreadable` refusal (V:4341–4343, 3537–3548). The completed intended batch can disappear unanswered. Replace that clause with:

   > The read and rename are separate steps: a batch published between them can be erased unread and unanswered. An in-place write can instead be read partially and refused; its remaining bytes can land on the replaced inode, losing the intended batch.

2. **Important — C’s delivery wording and endorsement of the retained paragraph remain too strong.** Draft:84–87 initially guarantees later publication; abandonment depends on exceeding **256 outstanding answers**, not elapsed time (V:3233–3245). Replace those sentences with:

   > An answer that could not be published remains owed and may be written later. Retrying publication can create another file with the same `seq`. If more than 256 answers are owed to your window, the oldest is given up and may never be written.

   Draft:90–91 also endorses `brief/PROTOCOL.md:75–78`, retaining “all produce one” despite abandonment. Its “submission time” is actually publication time (V:4446–4449). Replace that paragraph with:

   > The filename carries the publication time, your window name, and the command. Published refusals and successes share the same shape; read the contents to learn what happened.

3. **Minor — the v2 census qualification is still incomplete.** Draft:35 says “Anything else is claimed,” although preceding window checks can prevent intake (V:4220–4228, 3074–3091). Replace it with:

   > Once the window’s checks permit intake, every other shape takes the rewrite path:

   At Draft:107, replace “a non-map or missing `variables` while the map is known” with:

   > present non-map `variables`, or missing `variables` while the map is known

4. **Minor — G abbreviates away an essential discipline.** Draft:144–145 credits one writer plus rename alone with avoiding loss, although B correctly also requires waiting. Replace with:

   > Avoiding this loss requires one writer, publication by rename, and waiting for the far side’s cleared copy before replacing a claimable submission. The world does not enforce that discipline.

5. **Minor — two reconciliation details need precision.** Draft:117’s `2491–2515` omits the actual receipt append; replace with `2491–2516`. Draft:108’s “no verdict follows” should be:

   > No verdict from that newly claimed batch follows; an earlier deferral’s settlement can still be published.

   Evidence: V:3096–3105, 3536.

Check 1 — **PARTIAL:** the main v2 defects are addressed; the census qualification and result wording need the corrections above.

Check 2 — **SUPPORTED WITH CHANGES:** both answer-publication paths append receipt `seq`; acceptance and settlement have distinct receipts; duplicate publication and abandonment exist. C’s retained paragraph still overpromises files.

Check 3 — **PASS, within stated assumptions:** claim fsync → tick-row fsync → results (V:4369, 3124–3136). Adoption script:90 supplies `--state-dir`; current script:109–117 does not. No duplicate execution or answer preceding its durable decision was found in the inspected paths.

Check 4 — **PASS:** B specifies one writer, rename, waiting for the far side’s copy, ambiguous claim identity, and no next-read deadline.

Check 5 — **PASS WITH MINOR CORRECTIONS:** cited symbols and all three tests exist; fix finding 5.

Check 6 — **PASS:** V-1–V-3 identify real inconsistencies; F reserves vehicle ownership and adds no adoption prerequisite.

Check 7 — **PASS:** G explicitly disclaims Option B implementation, testing, adoption and qualification.

No edits, tests or collection, builds, containers, git mutations, or `.env` reads occurred.


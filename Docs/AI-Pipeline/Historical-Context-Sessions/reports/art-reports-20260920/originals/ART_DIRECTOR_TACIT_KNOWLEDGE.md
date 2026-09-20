# What an Art Director successor would lose: Vincent's taste, and the judgement no document states

Art Director Agent, 2026-09-18, for the Documentation Agent's handoff-pattern work. Everything here is **absent
from the art bible, the art guide, the inventories and memory** - it is what one session learned by watching
Vincent choose. Where a quote appears it is his own words.

## 1. Vincent's taste, from the picks he actually made

- **He picks the read, not the rendering.** Given three broken-masonry attempts he took the one whose *silhouette*
  said "collapsed", not the prettiest: "I pick masonry 3". Given two wizard hair variants he accepted the shorter
  one rather than paying to match: "feminine-dark's shorter hair - accept it", "accept the gap".
- **He will take a defect to keep a device.** He shipped `death_brute_decapitated_a` with a visible wound spiral
  after being shown that it conflicts with the stylised-not-gore direction he had approved an hour earlier. The
  device - a separate head-shaped piece beside the body - mattered more to him than the consistency.
- **"I want them both" is usually literal.** Offered a choice between two variants he takes both, and offered
  rejects he takes those too: "So we want all of the art :)". **Design for reuse rather than elimination** - when
  two candidates differ, look for a reading where each is a distinct thing (the two upright wraith cloaks became
  `hollowed` and `draining`) before proposing one as a reject.
- **Cost does not drive his art decisions.** "raise the cap, cost doesnt matter much on art, raise it 40" and
  "100 for the fireball, they wont need that much". He sets caps as ceilings he expects you to come under, not
  budgets to spend. Coming in at 27 of 100 pleased him; it is not read as under-delivery.
- **He notices scale before he notices quality.** His two unprompted complaints this week were "the fireball that
  shot out wasnt bigger" and a large wizard against a small door. **Check every new asset against a character at
  1:1 screen pixels before showing it to him**, because that is the comparison he makes.
- **He asks for feel, not features:** "We also want the player to like glow when they are charged up like in
  DBZ", "Corpse sprite that looks blasted, bloody, decapitated, burned, arm chopped off". Translate the feel into
  the device that survives 90 screen pixels, and tell him what you translated and why.
- **He answers fast and in fragments.** "1) approve 2) approve", "I want them both", "Awesome!!". Number your
  questions, keep them to one line each, and never send two rounds where one would do.

## 2. What he rejected, and why it was rejected

- **A "broken sluice" canon sentence** attributed to me that I had not written - stopped before landing. **Check
  whether quoted text is actually yours before defending it.**
- **A v1 canon clause** of my own, "a painted platform is scenery": correct in context, but quotable against the
  walkable ledge he asked for hours later. Replaced with the relationship form. See
  `write-rules-about-relationships-not-things`.
- **A wizard rebuild** whose v3 interpolation removed the walk stride - recorded as unusable rather than shipped.
- **Two upright wraith cloaks** I rejected as "reads alive" - **he overruled me**, and he was right that a
  spectral cloak can die standing. My rejection was a style judgement where the creature's nature was the better
  argument.

## 3. Judgement calls made constantly that no document states

- **Prompt discipline: forbid the noun, four ways.** A hooded cloak is drawn upright unless you say "lying
  completely flat", "spread out like dropped laundry", "the hood lies flat and empty", "nothing is standing, there
  is no figure wearing it". And **naming a fluid invites the fluid** - "a small dark plum-red pool" produced
  salmon and magenta blood; removing the noun entirely produced the right thing.
- **Pin both halves of a spec in the same prompt.** Fixing a silhouette alone lets the palette drift, and fixing
  the palette alone lets the silhouette drift. The masonry needed silhouette *and* palette pinned together on the
  third attempt.
- **Re-check the colour-locked file before condemning a composition.** A shared `reduce_colors` palette pulled
  round 1's salmon blood to plum and saved the only sprite with a legible severed arm. Judging the raw generation
  cost me a nearly-wrong reject.
- **The canvas is not the scale.** PixelLab pads to a square, so compare **drawn figures** via the alpha bbox. See
  `measure-the-drawn-figure-not-the-canvas`.
- **Alignment before beauty.** Every character-like set gets its lowest opaque row onto one row by whole-pixel
  shifts, then one pivot for the set: `(H - (row + 1)) / H`. A per-frame pivot mismatch between two sets of the
  same creature is the defect that reads as floating or hopping, and it is invisible in a contact sheet.
- **Emissive and painted-ground art promise things the game may not deliver.** Lit candles imply light the room
  does not cast; a painted floor disc under a door implies walkable ground. Flag both rather than fixing them
  silently - they are Vincent's calls.
- **Never hand-paint.** PixelLab generates; local work is limited to whole-pixel shifts, palette locks and
  measurement. A defect that cannot be fixed that way is a re-roll or a question, never a brush.
- **Show, then recommend, then let him choose.** Every package is native pixels + gameplay scale + one measured
  recommendation with its caveat named. He decides in one message when given that shape.

## 4. Spend bookkeeping a successor must not lose mid-batch

- **A total is a subtraction between two recorded `get_balance` readings, both taken with `list_jobs` empty.**
  Quote the pair beside the number: "4381/618 before, 4309/690 after, 690 - 618 = 72". Check both columns; they
  can disagree by one when fractional `reduce_colors` charges round separately.
- **Log every call as you make it** - id, canvas, seed, printed quote - because the meter cannot be split between
  two lines of work afterwards. That already cost one unattributable window when the NSC-078 pilot and the
  NSC-064 kit trial shared a reading.
- **Take a reading between two lines of work**, not only at the ends of a session.
- **Printed quotes are per-canvas and lower than the guides assume:** 5 at 48x48 and 96x96, 6 at 124x112 and
  144x96. `animate_object` prints no quote at all - measure the batch total instead of guessing per animation.
- **Never turn one run's ratio into a rate.** One batch ran 36% above printed; the next two ran level.
- **The cap is the stop.** Past it, stop and ask - and if a second re-roll round would breach it, send both
  versions to Vincent instead of spending.
- **Mid-batch crash recovery:** the per-task plan file is the source of truth, not the session. Object ids and
  seeds go into it as the calls are made, so a successor can download results with the archive endpoints
  (`/mcp/objects/<id>/download`) without re-generating anything. Signed per-frame URLs expire; archive endpoints
  do not.

## 5. Two things the transcript pass recovered from before the compactions

- **His technique for a detail that must appear on every facing: "Paint the book onto the front view first, then
  rebuild" (09-17 21:32).** Put the detail on the front view, then regenerate the rotations from it - do not
  inpaint eight facings one at a time. It is cheaper, it keeps the detail consistent, and it is how the wizard's
  belt book was done. Applies to any badge, scar, held object or costume change, and **it is not in the bible or
  the art guide** - worth landing there.
- **When he has already told another agent something: "I already spoke to GER about it, can you confirm with
  them?" (09-18 07:15).** Reconcile with that agent rather than re-asking him. Doing exactly that caught a real
  misreading - the GER Agent had heard his "pick the other" as a severity pair rather than as which look - so
  this is not politeness, it is how a divergence gets found before a crew implements two different rules.

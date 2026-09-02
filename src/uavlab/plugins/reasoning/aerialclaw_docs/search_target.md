# Search for a semantic target

Use incremental closed-loop coverage, never a precomputed full flight program.

1. Scan through new headings first. Use one bounded full-turn scan from each
   viewpoint (for example 1.5 rad/s for 5 s); do not spend another semantic
   turn rescanning headings already covered.
2. If no target is visible after a full local scan, choose an unvisited point
   from the BODY-derived coverage reference. It is a set of safe observation
   options, not a command sequence. Select one option and call `goto` with its
   provided absolute `goto_args`; do not put those absolute coordinates into
   relative `move` arguments. Then scan from the new point before choosing
   another option.
3. After every move, reconsider live detections. A target-labelled candidate
   with stronger score is better supported than a weaker candidate, but a score
   is not identity proof. Avoid stopping at the first weak lure when other
   search area remains.
   Only a detection whose label exactly matches the mission target label is a
   target candidate. A `distractor_*` or any other differently named detection
   is context, never a reason to approach or declare completion.
4. When the best supported target is visible, call `goto` to its reported
   position. Declare `done` only after arrival with low speed. If the
   BODY-derived mission-completion evidence is `supported: true`, declare
   `done` immediately instead of issuing another goto or scan.
5. No detection is not a dispatch failure. Do not declare `stuck` while an
   unvisited coverage option remains.

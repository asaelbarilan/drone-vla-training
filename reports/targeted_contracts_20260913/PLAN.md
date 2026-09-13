# D-107 targeted contracts and ordered-task extension

Authorized: isolate and repair C1 scan/perception and C5 arrival/stop, one flight
after each repair; then connect requested visual tools to red-then-blue mission.
At most three real flights: C1 search, C5 visible target, C1 ordered visit. Each
uses local pinned Gemma, seed 1061, unchanged scene/scoring and 60 s horizon.
No cloud, model changes, semantic truth inputs or adaptive reruns. Each change
gets offline positive/negative tests, a separate commit, then its single flight.
Retain all outcomes including timeouts. Do not claim architecture equivalence:
observed-view search and persistent arrival evidence are named opt-in variants.
Ordered task changes the public task contract, not classical route selection.

## Explicit amendment after exact-input/availability review

The initial three-flight cap was assistant-imposed, not a user restriction. Two
concrete implementation mistakes discovered in final audit justify two additional
and final flights (five total), communicated to the user before launch:
1. Ordered prompt accidentally retained passive-perception/full-turn advice.
2. Arrival TTL used capture-time eligibility but expired before model availability.
Remove the conflicting ordered strategy; use a 4 s anchor lifetime (two existing
monitor periods) with the same live arrival/range/identity gates. Offline replay
must cover availability as well as capture time before either final flight.
No further retries or open-ended tuning; all prior failures remain preserved.

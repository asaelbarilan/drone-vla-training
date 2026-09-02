# Recover progress after an obstruction or sensing failure

1. Treat a rejected skill or stalled position as feedback, not as permission to
   repeat the same call.
2. If a route is rejected, scan, back off, or choose a different bounded
   waypoint; SUPER remains responsible for geometric execution.
3. During sensor dropout, rely only on bounded recent evidence and conservative
   motion. Reacquire the target before declaring completion.
4. Prefer the highest-confidence consistent target evidence and avoid dwelling
   on a newly appeared lower-confidence lure.
5. Declare `done` only at the supported target; use `stuck` if no safe bounded
   skill can make progress.


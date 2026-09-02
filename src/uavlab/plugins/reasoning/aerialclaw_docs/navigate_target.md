# Navigate to a named semantic target

1. If a detection matching the instruction is visible, use `goto` to its
   reported ENU position and name the label. Do not substitute a distractor.
2. While travelling, inspect the new passive detections and runtime feedback on
   every cycle; do not resend a rejected call unchanged. `accepted` or
   `waypoint planned` means execution began, never that arrival occurred.
3. If the target temporarily disappears, use bounded semantic memory rather
   than inventing a new position. Use one bounded full-turn scan if no target
   evidence remains. If that scan still yields no target, choose an
   unvisited BODY-derived reconnaissance option with its absolute `goto_args`,
   then scan again from that new viewpoint.
4. Declare `done` only when the current position is within roughly 1.5 m of the
   best live or fresh remembered target and speed is low. A target that just
   left the field of view is not lost if bounded memory still places it at the
   vehicle. Reaching a planner backup endpoint is not mission completion.

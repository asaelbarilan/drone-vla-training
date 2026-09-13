# Corrected search validation: inspected before continuing

Run frozen_c1_turn_search_20260913_s1061: timeout at 60 s, 0 collisions or violations,
final 30.328 m. Corrected prompt present in exact saved requests. 4 completed text
calls, 1 perception call, 1 cancelled policy request at horizon. No runtime error.

Dashboard replay matched all 1,200 poses; source images present. Inspected camera,
map and motion at 0, 10, 11, 13.45, 22, 40.2 and 60 seconds in Edge. Screenshot at
10 seconds shows the red target clearly during rotation. Exact perception input
call-000003 at source 21.95 s (request starts 22 s) contains only sky and ground.
Its visible=false response is visually correct for THAT image.

Observed chain: scan requested at 0, available 8.5 s, rotates 7.5 radians until
13.5 s. Detector requested next and receives one post-scan frame at 21.95 s.
After negative detection model requests another scan. Parent hard protocol rejects
it: "scan violates the active search soft skill because a full local turn is already
complete and unvisited coverage options remain; choose goto." Model then selects
coverage point (21.1, 0, 6). Execution completes; next model request is cancelled.

Demonstrated integration conflict: angular coverage is counted as completed search
although intermediate views were never inspected by perception, and retry advice
conflicts with the inherited scan gate. Also initial model action ignored inspect
advice. This does not establish whether fixing the conflict alone would succeed.
No source/configuration change: continue frozen comparison, preserve this failure.

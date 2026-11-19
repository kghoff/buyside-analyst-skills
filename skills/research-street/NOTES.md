# research-street: why things are the way they are

## Peer documents, 2026-11-18
- The ABT run listed Dexcom's and Boston Scientific's Q3 calls as "blocked web pages" although DXCM's were on disk. Now
  agents request a competitor's call or filing in `doc_requests.txt`; step 2.3 fetches it with collect-documents'
  targeted fetch (local first) and resumes the agent.
- Peers live in each agent's `peer_docs.json`, read by `p2common.peer_items`, not in run.json: preflight rewrites
  run.json every run and would drop them.
- p2check lets an agent cite only the peer documents fetched for it, as readers may cite only their group's reports.
- Weighting: a peer's facts about its own business are facts (`official`, like a regulator); its claims about the
  market or the subject are an interested party's opinion, below tier 1 (the ABT PM review, challenge R1).
- render.py can't tell a peer's call (`2026 Q3 DXCM call`) from a company document by its label, so step 8 passes the
  peer labels with `--outside-labels`.

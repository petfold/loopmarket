# Recordings

Terminal recordings of `examples/demo_federation.py` against a live Bee
node (Swarm Desktop 2.8.2, light node, Gnosis mainnet), made with
util-linux `script`. Replay at real speed, or faster:

```
scriptreplay -t demo_federation-live-20260904-2353.timing demo_federation-live-20260904-2353.log
scriptreplay -t demo_federation-live-20260904-2353.timing demo_federation-live-20260904-2353.log -d 20
```

- `demo_federation-live-20260904-2353` — the full run, green: core-pack
  catalogue (4,157 categories) committed to Swarm in 41 s, three maker
  feeds, two honest aggregators byte-identical, Cain convicted by the
  audit, the triangle settled, follower reads six fills. 20 min 52 s
  wall clock, most of it feed probes on a light node: an
  exists-check for a not-yet-written feed chunk costs ~4 s and
  sometimes a transient `500 read chunk failed`, retried by the demo.
- `demo_federation-live-20260904-2341-failed` — the run before the retry
  existed: died on the first such 500 at Bruno's feed commit. Kept as
  the evidence for why `committed()` retries.

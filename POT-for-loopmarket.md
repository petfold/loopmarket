# What loopmarket would need from POT

*Untracked working note for Viktor Trón and Viktor Tóth, 2026-08-21.
Context: loopmarket's proof-route decision (docs/plans/proof-fabric.md),
ratified this week as "recordstore trie proofs first, POT conditional."
We hear recordstore↔POT convergence is planned and POT is still moving —
this note is the consumer's requirements list, so the convergence can be
designed against a real downstream instead of a guess.*

## The consumer in one paragraph

loopmarket is a combinatorial marketplace: content-addressed offers in a
versioned recordstore keyspace (the "book"), solvers hunting exchange
loops against **pinned 32-byte roots**, and a settlement layer that
re-verifies everything. In P2, part of that verifier becomes a Gnosis
Chain contract: it receives a proposed loop plus proofs that every offer
**is** in the pinned book root and that its fill **is not**. So the proof
system's job is: testify about key presence *and absence* under a root
the whole pipeline already pins (our invariants U4/U10), to a verifier
that may be an EVM contract with no store access.

## Why the ruling went trie-first (what POT would have to match)

recordstore ≥0.16.0 ships `prove`/`verify_proof` over the very trie the
book lives in: self-describing envelope of raw trie-node blobs,
verification = hash-chain recomputation against the 32-byte root, no
store access, O(depth), absence provable because the encoding is
canonical (one root, one possible location per key). POT today would
testify about a *mirror* of our book, and the mirror's fidelity becomes a
new proof obligation. That — not any dislike of BMT — is what decided it.

## Requirements, in order of force

1. **Proofs about the canonical root, not a copy.** Either convergence
   makes the POT root *be* (or deterministically derive from) the
   recordstore canonical root — equal content ⇒ equal root, order- and
   history-independent — or there is a proven two-directional
   root-correspondence primitive. "The mirroring code is correct" is not
   dischargeable; a completeness claim over every key is.
2. **Absence proofs, first-class.** Non-monotone claims must name a root,
   and our settlement's core checks are absences ("no fill for offer X in
   root R", "offer Y is not in the book"). This needs a canonical
   encoding where a key has exactly one possible location, so exhibiting
   the path where it *would* live proves it isn't there. Inclusion alone
   is half a proof system for us.
3. **Store-free, byte-exact verification.** `verify(proof, root)` with no
   node access: the envelope carries the raw exhibited bytes and the
   verifier recomputes hashes over *those exact bytes* — never
   re-serialization (canonicalization drift must be impossible by
   construction). Self-describing format name + version, so readers skip
   unknown formats instead of misreading them.
4. **On-chain cost, measured not estimated.** We could find no published
   gas numbers for `assertForkPathProof`. Our adoption gate requires
   self-benchmarked gas on Gnosis; the research envelope we carry (tens
   of thousands of gas per path node; a 500k-gas verification ≈ $0.0001
   at 0.2 gwei xDAI) is an estimate we would love to replace with your
   numbers. Batch verification matters to us: one settled beat can need
   inclusion + fill-absence proofs for dozens of keys under one root, so
   per-proof fixed costs dominate calldata.
5. **A pinnable, conformance-testable release.** A tagged release we can
   pin, published proof test vectors (valid + adversarial), and
   regression tests covering the fork-counting / segment-index class of
   bugs fixed in 2026. Our gate G4 requires vetting a pinned commit with
   our own conformance tests either way — published vectors make that
   cheap for every consumer, not just us.

## What would make POT actively attractive (beyond parity)

- **b33son-style field-level disclosure.** If offer records adopt a
  canonical, 32-byte-segment-aligned encoding whose BMT proofs reveal a
  *single field*, disputes could disclose one field on-chain instead of
  the whole offer — directly useful to our privacy roadmap (P4). This is
  the one capability the recordstore route does not have a story for.
- **keccak-native paths.** BMT over keccak is EVM-native; if converged
  proofs keep that, the on-chain verifier gets cheaper than sha256-based
  recomputation. (Our current trie proofs would need sha256 on-chain —
  precompiled, but keccak is cheaper still.)
- **Proof-size bounds** as a function of book size, so we can budget
  calldata per beat at design time.

## What we can offer back

A real, running consumer: a pinned-root discipline end-to-end, a live
Gnosis-mainnet book (the 2026-08-01 settled triangle, gated test in-repo),
and — once P2 contract work starts — gas measurements and conformance
vectors from our side. Our adoption gate re-opens automatically when the
convergence ships: requirement 1 dissolves by construction, and what
remains is exactly items 4 and 5.

## A second ask: an enumerable announcement set ("super-GSOC")

Separate from proofs, one more primitive would remove our last
non-Swarm dependency. Our federated book needs makers to announce "my
book is (owner, topic)". GSOC today is *messaging*: delivery to one
listening full node, per-aggregator mined id, no delivery guarantees —
so for an *objective* announcement set (needed to make aggregator
completeness checkable and paid-listing censorship provable) we
currently fall back to Gnosis registry events. What the marketplace
actually wants is Swarm-native:

- **A set, not a stream**: announcements as *stamped, stored* chunks
  under a derivable address family (topic, epoch, shard), pull-readable
  forever — no listener liveness, and postage is the spam floor, priced
  by the network itself.
- **Enumerable**: any full node in the address family's neighbourhood(s)
  can serve "all announcements for (topic, epoch)" — which makes any
  aggregator's input set publicly auditable, and "charging for
  inclusion" a provable, reputation-fatal act rather than a norm
  violation.
- **Sharded** by epoch/region so no single neighbourhood becomes the
  global hot spot or DoS target.

If GSOC's evolution (or a pub/sub successor) grows these properties, we
drop the on-chain registry to true-fallback status and publication
becomes a protocol property of Swarm. We can offer burn-in loss
measurements against the registry-event ground truth as consumer
evidence, per the thresholds in our
`docs/plans/P1-federated-book.md` §4.

*References: loopmarket `docs/plans/proof-fabric.md` (decision rule, gate
G4, upstream watch), `ARCHITECTURE.md` §8; recordstore ≥0.16.0
`prove`/`verify_proof`; ontodag `docs/CONTRACT.md` §7 (envelope policy);
`docs/plans/P1-federated-book.md` §4 (announcements), threat register
T14 (aggregator omission).*

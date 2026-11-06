# Adaptive checkpoint compression

The accepted 02:49 UTC checkpoint grew to 123,506,840 archive bytes as the frozen
qualification programme continued. Its isolated restore is 328,445,952 SQLite
bytes. This is below the unchanged 150/500/750 MB recovery limits but approaches
the existing 130 MB bulk-work guard.

On the same fixed checkpoint, fresh archive copies measured 123,625,933 bytes at
gzip level 1, 113,729,890 at level 6 and 112,635,443 at level 9. The best trial
restored with all 36 tables byte-equivalent, including rows stored as compressed
metadata. Source captures also passed the standard hash checks. Local timings are
recorded as local evidence, not deployed CPU or latency. No provider calls,
retention changes, quota increases or fact pruning were used.

The repair retains fast level-1 compression for smaller maintenance checkpoints.
When the resulting archive exceeds 120 MB (or the transfer limit, if lower), it
recompresses the same isolated SQLite snapshot and frozen capture-file set at
level 6 before enforcing the existing transfer ceiling. It does not take a second
SQLite backup or collect later capture files during fallback. Later live writes
belong to the next checkpoint. Explicit level-6/9 calls keep their existing path.

The patched fast path itself subsequently produced 113,729,911 bytes after
level-1/level-6 passes on that fixed restore. A second isolated restore matched
all 36 tables byte-equivalently; see `adaptive-checkpoint-proof.json`.

A regression adds a live database write and capture after the first archive, then
proves the fallback restores the original consistent snapshot under a transfer
ceiling the fast archive cannot meet. Another proves an oversized fallback still
fails closed and retains the previous accepted archive. Required checks and fresh post-deploy recovery subsequently passed for
`fc71d10`; see `combined-release/`. Natural maintenance-checkpoint observations
remain distinct from manual level-6 backup evidence.

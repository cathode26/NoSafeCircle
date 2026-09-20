"""Point the state file's NSC-078 entry at v3, the authoritative patch."""
import io

path = r'C:\NSC\agent-state\game-agent.md'
lines = io.open(path, encoding='utf-8', newline='').read().split('\n')

start = next(i for i, line in enumerate(lines) if 'commit-nsc078-plan-patch.ps1' in line)
end = next(i for i in range(start, len(lines)) if lines[i].lstrip().startswith('3. The Lower Vault'))

replacement = [
    '2. ~~NSC-078 meter-caveat patch~~ **handed to the Documentation Agent** - doc commits are their',
    '   lane, and "my writes are refused" was the wrong reason to hand it over (runbook rule 16).',
    '   Three versions existed; **v3 is authoritative**:',
    '   `217a167239232b2e65f178b9e4e22267e4b27e770d53ac154d5942498b2b1806`, 48471 bytes, LF - verified',
    '   independently in a scratch repo and matching the Art Director byte for byte. v1',
    '   (`5a68a8fd...`) and v2 (`d798cd2e...`) are superseded. Settled figures: **97 printed against',
    '   132 metered, 1.36**, derived from balance readings 331 -> 463 across 22 calls rather than by',
    '   hand; the earlier 95/130 was the same measurement read one call early.',
    '   **The GER Agent has rebound rev 6 to v3.** That mattered because a gate pinned to a',
    '   superseded hash fails closed and reads as "nothing happened" - rev 6 and the prop pilot cap',
    '   would have sat blocked invisibly.',
    '   **Do not run `commit-nsc078-plan-patch.ps1`; it applies v1.**',
]

io.open(path, 'w', encoding='utf-8', newline='').write('\n'.join(lines[:start] + replacement + lines[end:]))
print('state file corrected: NSC-078 entry now points at v3')

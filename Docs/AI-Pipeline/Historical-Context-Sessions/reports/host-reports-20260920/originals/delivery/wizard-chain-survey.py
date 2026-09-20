"""Survey what the five wizard-chain evidence passes actually cost.

For each task: its completion gates, which need Vincent personally, whether a validation policy
entry exists, and - the lesson from NSC-069 - whether the entry's test filter names types that
actually exist in the tree. A filter naming a missing type selects zero tests and reports success.
"""
import json
import re
import subprocess

GIT_DIR = r'C:\NSC\NSC\NoSafeCircle\.git'
NO_WINDOW = 0x08000000
TASKS = ['NSC-089', 'NSC-091', 'NSC-045', 'NSC-061']


def git(*args):
    return subprocess.run(['git', '--git-dir', GIT_DIR] + list(args),
                          capture_output=True, creationflags=NO_WINDOW).stdout


policy = json.loads(git('cat-file', '-p', 'main:Pipeline/TaskReviewAgent/authoritative_validation_policy.json'))
tree = git('ls-tree', '-r', '--name-only', 'main').decode('utf-8', 'replace').splitlines()
sources = [p for p in tree if p.endswith('.cs')]

declared = set()
for path in sources:
    body = git('cat-file', '-p', 'main:' + path).decode('utf-8', 'replace')
    for match in re.finditer(r'\b(?:class|struct)\s+([A-Za-z_][A-Za-z0-9_]*)', body):
        declared.add(match.group(1))

for task in TASKS:
    raw = git('cat-file', '-p', 'main:Tasks/%s.yaml' % task)
    if not raw:
        print('%s: NOT FOUND' % task)
        continue
    contract = json.loads(raw)
    entry = policy.get('tasks', {}).get(task)

    print('=' * 78)
    print('%s  rev %s  %s' % (task, contract.get('contract_revision'), (contract.get('title') or '')[:52]))

    gates = contract.get('completion_gates', [])
    human = []
    for gate in gates:
        text = gate.get('requirement') or ''
        needs_vincent = bool(re.search(r'\bVincent\b', text))
        if needs_vincent:
            human.append(gate.get('gate_id'))
        print('  %s%s %s' % (gate.get('gate_id'), ' [VINCENT]' if needs_vincent else '         ',
                             ' '.join(text.split())[:96]))
    print('  -> gates needing Vincent: %s' % (', '.join(human) if human else 'none'))

    if not entry:
        print('  -> POLICY ENTRY: MISSING - the GER Agent must add one before a run')
        continue

    bound = (entry.get('task_contract_sha256') or '')[:16]
    actual = subprocess.run(['git', '--git-dir', GIT_DIR, 'cat-file', '-p', 'main:Tasks/%s.yaml' % task],
                            capture_output=True, creationflags=NO_WINDOW).stdout
    import hashlib
    live = hashlib.sha256(actual).hexdigest()[:16]
    print('  -> policy binds %s, contract hashes %s : %s' % (bound, live, 'MATCH' if bound == live else 'STALE'))
    print('  -> platforms: %s' % ', '.join(entry.get('required_test_platforms') or []))
    for platform, filt in (entry.get('test_filters') or {}).items():
        for part in filt.split(';'):
            type_name = part.rsplit('.', 1)[-1]
            ok = type_name in declared
            print('     %-9s %-62s %s' % (platform, type_name, 'type exists' if ok else 'TYPE NOT FOUND'))

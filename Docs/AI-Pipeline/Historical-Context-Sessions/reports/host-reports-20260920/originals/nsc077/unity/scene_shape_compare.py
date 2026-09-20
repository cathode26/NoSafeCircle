import struct, sys, collections
def parse(path):
    b = open(path, "rb").read()
    data_offset = struct.unpack(">q", b[32:40])[0]
    p = 48
    def rd(fmt):
        nonlocal p
        v = struct.unpack_from("<" + fmt, b, p)[0]; p += struct.calcsize("<" + fmt); return v
    def cstr():
        nonlocal p
        q = b.index(b"\0", p); s = b[p:q].decode("utf-8", "replace"); p = q + 1; return s
    cstr(); rd("i"); tt = rd("?")
    types = []
    for _ in range(rd("i")):
        cid = rd("i"); rd("?"); sidx = rd("h")
        if cid == 114: p += 16
        p += 16
        n = rd("i"); ss = rd("i"); p += n * 32 + ss
        d = rd("i"); p += 4 * d
        types.append((cid, sidx))
    objs = []
    for _ in range(rd("i")):
        p = (p + 3) & ~3
        pid = rd("q"); start = rd("q"); size = rd("I"); ti = rd("i")
        objs.append((pid, types[ti][0], types[ti][1], size, b[data_offset + start:data_offset + start + size]))
    scripts = []
    for _ in range(rd("i")):
        fi = rd("i"); p = (p + 3) & ~3; lid = rd("q"); scripts.append((fi, lid))
    externals = []
    for _ in range(rd("i")):
        cstr(); g = b[p:p + 16]; p += 16; rd("i"); cstr(); externals.append(g.hex())
    def script_key(sidx):
        fi, lid = scripts[sidx]
        return (externals[fi - 1] if fi > 0 else "local") + ":" + str(lid)
    return [(o[0], o[1], script_key(o[2]) if o[1] == 114 else "", o[3], o[4]) for o in objs]

def shape(path):
    objs = parse(path)
    c = collections.Counter((o[1], o[2]) for o in objs)
    s = collections.defaultdict(list)
    for o in objs: s[(o[1], o[2])].append(o[3])
    return len(objs), c, {k: sorted(v) for k, v in s.items()}

n0, c0, s0 = shape(sys.argv[1])
print("base objects", n0, "distinct (class, script) keys", len(c0))
for other in sys.argv[2:]:
    n, c, s = shape(other)
    cd = {k: (c0.get(k, 0), c.get(k, 0)) for k in set(c0) | set(c) if c0.get(k, 0) != c.get(k, 0)}
    sd = [k for k in s0 if k in s and s0[k] != s[k]]
    print(other.replace("\\", "/").split("/")[-1], "objects", n, "| count diffs:", cd or "none", "| size diffs:", sd or "none")

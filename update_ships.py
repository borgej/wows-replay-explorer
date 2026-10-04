# Extracts ship names/tiers/types and bot names from the World of Warships install into ships.js,
# and downloads the WoWS Numbers expected values for Personal Rating into expected.js.
# Run again after a game update:  python update_ships.py [path-to-game]
import os, re, struct, sys, zlib, pickle, json

GAME = sys.argv[1] if len(sys.argv) > 1 else r'E:\Games\World_of_Warships'
HERE = os.path.dirname(os.path.abspath(__file__))
SPECIAL_GROUPS = {'special', 'specialUnsellable', 'ultimate', 'earlyAccess', 'event'}


def newest_build():
    builds = [d for d in os.listdir(os.path.join(GAME, 'bin')) if d.isdigit()]
    return max(builds, key=int)


def read_idx(path):
    """Parse a .idx archive index: returns ({full path: (pkg name, offset, size, unpacked size)})."""
    d = open(path, 'rb').read()
    n_nodes, n_files, n_vols, _ = struct.unpack_from('<IIII', d, 16)
    nodes_off, files_off, vols_off = struct.unpack_from('<QQQ', d, 32)
    base = 16
    nodes = {}
    for i in range(n_nodes):
        p = base + nodes_off + i * 32
        size, off, nid, parent = struct.unpack_from('<QQQQ', d, p)
        nodes[nid] = (d[p + off:p + off + size].rstrip(b'\0').decode(), parent)
    vols = {}
    for i in range(n_vols):
        p = base + vols_off + i * 24
        size, off, vid = struct.unpack_from('<QQQ', d, p)
        vols[vid] = d[p + off:p + off + size].rstrip(b'\0').decode()

    def full(nid):
        parts = []
        while nid in nodes:
            parts.append(nodes[nid][0])
            nid = nodes[nid][1]
        return '/'.join(reversed(parts))

    files = {}
    for i in range(n_files):
        p = base + files_off + i * 48
        rid, vid, off, _comp, _flags, size, _crc = struct.unpack_from('<QQQIIII', d, p)
        unpacked, = struct.unpack_from('<Q', d, p + 40)
        files[full(rid)] = (vols.get(vid), off, size, unpacked)
    return files


def extract(build, wanted):
    idx_dir = os.path.join(GAME, 'bin', build, 'idx')
    for name in os.listdir(idx_dir):
        if not name.endswith('.idx'):
            continue
        files = read_idx(os.path.join(idx_dir, name))
        if wanted in files:
            pkg, off, size, unpacked = files[wanted]
            with open(os.path.join(GAME, 'res_packages', pkg), 'rb') as f:
                f.seek(off)
                raw = f.read(size)
            return raw if size == unpacked else zlib.decompress(raw, -15)
    raise SystemExit(f'{wanted} not found in {idx_dir}')


class _Obj:
    def __init__(self, *a, **k): pass
    def __setstate__(self, state):
        if isinstance(state, dict):
            self.__dict__.update(state)


class _Unpickler(pickle.Unpickler):
    def find_class(self, module, name):
        if module == 'copy_reg' and name == '_reconstructor':
            return lambda cls, base, state: cls()
        if module.startswith('GameParams') or module in ('copy_reg', '__builtin__'):
            return _Obj
        return super().find_class(module, name)


def read_mo(path):
    d = open(path, 'rb').read()
    _magic, _rev, n, keys_off, vals_off = struct.unpack_from('<5I', d, 0)
    out = {}
    for i in range(n):
        kl, ko = struct.unpack_from('<II', d, keys_off + 8 * i)
        vl, vo = struct.unpack_from('<II', d, vals_off + 8 * i)
        raw = d[vo:vo + vl]
        try:
            val = raw.decode('utf-8')
        except UnicodeDecodeError:
            val = raw.decode('cp1252')
        out[d[ko:ko + kl].decode('utf-8', 'replace')] = val
    return out


def main():
    build = newest_build()
    print(f'Game build {build}')
    data = extract(build, 'content/GameParams.data')
    params = _Unpickler(__import__('io').BytesIO(zlib.decompress(data[::-1])), encoding='latin1').load()
    root = params.get('', params)
    texts = read_mo(os.path.join(GAME, 'bin', build, 'res', 'texts', 'en', 'LC_MESSAGES', 'global.mo'))

    # Icons and flags, copied into assets/ next to the page.
    files = {}
    idx_dir = os.path.join(GAME, 'bin', build, 'idx')
    for n in os.listdir(idx_dir):
        if n.endswith('.idx'):
            files.update(read_idx(os.path.join(idx_dir, n)))
    flags = {p[len('gui/nation_flags/tiny/flag_'):-4] for p in files if p.startswith('gui/nation_flags/tiny/flag_')}
    for sub in ('class', 'flags'):
        os.makedirs(os.path.join(HERE, 'assets', sub), exist_ok=True)
    for flag in flags:
        with open(os.path.join(HERE, 'assets', 'flags', f'{flag}.png'), 'wb') as f:
            f.write(extract(build, f'gui/nation_flags/tiny/flag_{flag}.png'))
    icons = 0
    for p in files:
        m = re.match(r'gui/service_kit/ship_classes/icon_default_([a-z]+)(_premium|_special)?\.png$', p)
        if m:
            with open(os.path.join(HERE, 'assets', 'class', f'{m[1]}{m[2] or ""}.png'), 'wb') as f:
                f.write(extract(build, p))
            icons += 1

    ships = {}
    for v in root.values():
        ti = getattr(v, 'typeinfo', None)
        if not ti or getattr(ti, 'type', None) != 'Ship':
            continue
        index = v.index
        name = texts.get(f'IDS_{index}') or v.name.split('_', 1)[-1].replace('_', ' ')
        # The game colours premium ships gold and special ships (coal, steel, research bureau...) orange.
        kind = 'p' if v.group == 'premium' else 's' if v.group in SPECIAL_GROUPS else 't'
        flag = index if index in flags else ti.nation if ti.nation in flags else ''
        ships[str(v.id)] = [name, getattr(v, 'level', 0), ti.species, ti.nation, index, kind, flag]
    missing = sorted({s[3] for s in ships.values()} - flags)
    if missing:
        print('No flag for nations:', missing)

    # Bots in operations/scenarios are named with text keys like IDS_OP_01_04_ATAKER_R11.
    names = {k: v for k, v in texts.items() if re.match(r'IDS_OP_\d', k) and 0 < len(v) <= 40}

    out = os.path.join(HERE, 'ships.js')
    with open(out, 'w', encoding='utf-8') as f:
        f.write('// Generated by update_ships.py from the game files. Do not edit.\n')
        f.write('// ships: id -> [name, tier, type, nation, index, kind (t=tech tree, p=premium, s=special), flag];\n')
        f.write('// names: bot name keys -> display name.\n')
        f.write('window.GAME_DATA = ')
        json.dump({'build': build, 'ships': ships, 'names': names}, f, ensure_ascii=False, separators=(',', ':'))
        f.write(';\n')
    print(f'{len(ships)} ships, {len(names)} bot names -> {out}; {len(flags)} flags, {icons} class icons -> assets/')


def update_expected():
    """Downloads the per-ship expected values WoWS Numbers uses for Personal Rating (PR) into expected.js."""
    import urllib.request
    url = 'https://api.wows-numbers.com/personal/rating/expected/json/'
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'wows-replay-viewer'})
        raw = json.load(urllib.request.urlopen(req, timeout=30))
    except Exception as e:
        print(f'Could not download PR expected values ({e}); keeping the existing expected.js')
        return
    data = {k: [round(v['average_damage_dealt'], 1), round(v['average_frags'], 4), round(v['win_rate'], 3)]
            for k, v in raw['data'].items() if v}
    out = os.path.join(HERE, 'expected.js')
    with open(out, 'w', encoding='utf-8') as f:
        f.write('// Generated by update_ships.py from api.wows-numbers.com. Do not edit.\n')
        f.write('// data: ship id -> [expected damage, expected frags, expected win rate %].\n')
        f.write('window.PR_EXPECTED = ')
        json.dump({'time': raw.get('time'), 'data': data}, f, separators=(',', ':'))
        f.write(';\n')
    print(f'{len(data)} ships with PR expected values -> {out}')


if __name__ == '__main__':
    main()
    update_expected()

# Builds index.html from src/app.html by inlining the Blowfish constants (hex digits of pi).
import os
here = os.path.dirname(os.path.abspath(__file__))
N = 1042 * 32 + 64
def arctan_inv(x, one):
    s = t = one // x; x2 = x * x; n = 3; sign = -1
    while t:
        t //= x2; s += sign * (t // n); sign = -sign; n += 2
    return s
one = 1 << (N + 32)
pi = 4 * (4 * arctan_inv(5, one) - arctan_inv(239, one))
h = format((pi - 3 * one) >> 32, 'x').zfill(N // 4)
words = [int(h[i * 8:i * 8 + 8], 16) for i in range(1042)]
assert words[0] == 0x243f6a88 and words[-1] == 0x3ac372e6
rows = [','.join('0x%08x' % w for w in words[i:i + 8]) for i in range(0, 1042, 8)]
const = '// Blowfish P-array + S-boxes: the hex digits of pi.\nconst BF_INIT = new Uint32Array([\n' + ',\n'.join(rows) + ']);'
src = open(os.path.join(here, 'src', 'app.html'), encoding='utf8').read()
open(os.path.join(here, 'index.html'), 'w', encoding='utf8').write(src.replace('/*BF_INIT*/', const))
print('index.html written')

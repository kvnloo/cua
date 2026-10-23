# Experimental finite semantic model; inputs are assumptions, never permissions.
# IDs: OPEN TYPE KEY DARK_MODE FOLDER TIMER SCREENSHOT EVENT DONE UNKNOWN.
# Bits: fresh grant unique calculator focus complete confirmed supported.
import Base

def has(+s: U32, +mask: U32) -> U32:
  Bool.to_u32(U32.is_eq((s .&. mask : U32), mask))

def eq(a: U32, b: U32) -> U32:
  Bool.to_u32(U32.is_eq(a, b))

def guard(+s: U32, +a: U32) -> U32:
  +normal = (has(s, 135) * Bool.to_u32(U32.is_lt(a, 8)) : U32)
  +typing = Bool.pick(U32, U32.is_eq(a, 1), has(s, 24), 1)
  +event = Bool.pick(U32, U32.is_eq(a, 7), has(s, 64), 1)
  +done = (eq(a, 8) * has(s, 33) : U32)
  +unknown = (eq(a, 9) * has(s, 1) * eq((s .&. 128 : U32), 0) : U32)
  ((normal * typing * event) .|. done .|. unknown : U32)

def robust(+s: U32, +a: U32) -> U32:
  (guard(s, a) * guard((s .^. 8 : U32), a) * guard((s .^. 16 : U32), a) * guard((s .^. 24 : U32), a) : U32)

def candidates(+x: U32) -> U32:
  +s = (x .&. 255 : U32)
  +a = ((x >> 8n) .&. 15 : U32)
  +v = (robust(s, a) .|. (robust(s, ((a + 1) .&. 15 : U32)) << 1n) .|. (robust(s, ((a + 2) .&. 15 : U32)) << 2n) .|. (robust(s, ((a + 3) .&. 15 : U32)) << 3n) : U32)
  v

def point(+mode: U32, +x: U32) -> U32:
  Bool.pick(U32, U32.is_eq(mode, 0), guard((x .&. 255 : U32), ((x >> 8n) .&. 15 : U32)), candidates(x))

def leaf(n: Nat, +mode: U32, +x: U32, acc: U32) -> U32:
  match n:
    case 0n:
      acc
    case 1n+p:
      leaf(p, mode, (x + 1 : U32), (acc + point(mode, x) : U32))

def tree(d: Nat, +mode: U32, +k: U32, +lw: Nat, +w: Nat) -> U32:
  match d:
    case 0n:
      leaf(w, mode, (k << lw : U32), 0)
    case 1n++p:
      a b = tree(p, mode, (k << 1n : U32), lw, w) tree(p, mode, ((k << 1n) .|. 1 : U32), lw, w)
      (a + b : U32)

def vectors(d: Nat, +mode: U32, +k: U32) -> Array<U32>:
  match d:
    case 0n:
      ALeaf{point(mode, k)}
    case 1n++p:
      a b = vectors(p, mode, (k << 1n : U32)) vectors(p, mode, ((k << 1n) .|. 1 : U32))
      ANode{a, b}

import Base
import ./model.bend as M

def run(n: Nat, +seed: U32) -> IO(Unit):
  match n:
    case 0n:
      IO.pure(Unit, Unit{})
    case 1n+p:
      do IO<Unit>:
        start : Nat <- IO.now()
        value : U32 <- IO.pure(U32, M.tree!(14n, 1, seed, 6n, 64n))
        finish : Nat <- IO.now()
        IO.print(U32.show(value) ++ "," ++ Nat.show(Nat.sub(finish, start)))
        run(p, (seed + 1 : U32))

def main() -> IO(Unit):
  run(5n, 0)

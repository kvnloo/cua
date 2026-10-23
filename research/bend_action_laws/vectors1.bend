import Base
import ./model.bend as M

def emit(xs: List<U32>) -> IO(Unit):
  match xs:
    case Nil{}:
      IO.pure(Unit, Unit{})
    case Con{h, t}:
      do IO<Unit>:
        IO.print(U32.show(h))
        emit(t)

def main() -> IO(Unit):
  emit(Array.to_list(~U32, M.vectors!(12n, 1, 0)))

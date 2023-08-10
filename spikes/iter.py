class Mc:
    def __init__(self, qty):
        self.i = 0
        self.qty = qty

    def mf(self) -> int|None:
        if self.i < self.qty:
            self.i += 1
            return self.i
        return None


mc = Mc(5)
ml = list(iter(mc.mf, None))
print(ml)


def omf(qty):
    i = 0

    def imf():
        nonlocal i
        if i < qty:
            i += 1
            return i
        else:
            return None
    return imf


print(mj := list(iter(omf(5), None)))
print(mk := list(iter(omf(3), None)))


from itertools import islice


def chuck(a, n):
    ia = iter(a)
    return iter(
        lambda : tuple(
            islice(ia, n)
        ),
        ()
    )


a = [1, 2, 3, 4, 5, 6]
print(nl := list(chuck(a, 2)))


def charles(a: list[int]):
    ia = iter(a)
    def chuckie():
        nonlocal ia
        return next(ia), next(ia)
    return list(iter(chuckie, ()))


print(pl := charles(a))

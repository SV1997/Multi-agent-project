# scripts/taxonomy/labels.py

def resolve(numbers: list[int], candidates: list[str]) -> list[str]:
    """Turn the model's numbers into category names.

    A number outside the list is dropped. If nothing valid is left, keep all the
    candidates: a chunk that is labelled too widely is still found by a search,
    but a chunk labelled with nothing (or the wrong thing) can never be found.
    """
    picked = []
    for n in numbers:
        if 0 <= n < len(candidates) and candidates[n] not in picked:
            picked.append(candidates[n])
    return picked or list(candidates)

def test_resolve():
    cands = ["a", "b", "c"]
    assert resolve([2, 0], cands) == ["a", "c"]
    assert resolve([1, 1, 1], cands) == ["b"]
    assert resolve([7, -1], cands) == ["a", "b", "c"]
    assert resolve([], cands) == ["a", "b", "c"]
    assert resolve([1, 9], cands) == ["b"]

if __name__=="__main__":
    test_resolve()
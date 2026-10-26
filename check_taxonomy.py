import copy, yaml
from shared.taxonomy.taxonomy import parse_taxonomy, TaxonomyError

good = yaml.safe_load(open("shared/taxonomy/policy_taxonomy.yaml", encoding="utf-8"))
parse_taxonomy(good)                         
print("real file OK")

def attempt(label, change):
    data = copy.deepcopy(good)               
    change(data)
    try:
        parse_taxonomy(data)
        print(f"{label}: NOT CAUGHT")
    except TaxonomyError as e:
        print(f"{label}: caught ->", str(e).splitlines()[1].strip())


if __name__ == "__main__":
    attempt("typo in a category", lambda d: d["hr"]["documents"]["tmpueqswgxe.md"]["categories"].__setitem__(0, "facilties_register"))
    attempt("cycle",              lambda d: d["hr"]["categories"]["leave"].update(parents=["earned_leave"]))
    attempt("category nobody uses", lambda d: d["hr"]["documents"].pop("tmpueqswgxe.md"))
    attempt("missing description",  lambda d: d["hr"]["categories"]["leave"].update(description=""))


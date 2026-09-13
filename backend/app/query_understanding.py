"""Conservative lexical constraints, not an object detector or model call.

Only explicit positive mentions in final reviewed text/tags are evidence.
Unknown/ambiguous entities stay semantic; this deliberately favors precision.
"""
import re

ENTITIES = {
    "cat": ("小猫", "猫咪", "猫", "kitten", "kittens", "cat", "cats"),
    "dog": ("小狗", "狗狗", "狗", "puppy", "dog", "dogs"),
    "bird": ("鸟类", "小鸟", "鸟", "bird", "birds"),
    "person": ("人物", "人像", "行人", "person", "people"),
    "car": ("汽车", "轿车", "car", "cars"),
}


def mention_pattern(aliases):
    return "|".join(r"\b" + re.escape(term) + r"\b" if term.isascii() else re.escape(term)
                    for term in aliases)


def mentions(text: str, aliases) -> bool:
    # Reject ambiguous/negated clauses and compound Chinese homonyms.
    for clause in re.split(r"[。！？.!?;；\n]", text.lower()):
        if re.search(r"没有|并非|不是|不含|无|可能|似乎|像是|类似|如同|猫头鹰|熊猫|海狗|no\b|not\b|without\b|maybe\b|resembles\b", clause):
            continue
        if re.search(mention_pattern(aliases), clause):
            return True
    return False


def reviewed_entities(result, revision) -> set[str]:
    # Never resurrect superseded AI summary/observations after a human edit.
    text = "\n".join([*(revision.tags if revision.tags is not None else result.tags),
                       *(f"{d.observation}\n{d.interpretation}" for d in revision.dimensions)])
    return {code for code, aliases in ENTITIES.items() if mentions(text, aliases)}


def understand(query: str | None, available: set[str]) -> dict:
    text = query or ""
    recognized = [code for code, aliases in ENTITIES.items() if mentions(text, aliases)]
    applied = [code for code in recognized if code in available]
    remaining = text
    for code in applied:
        remaining = re.sub(mention_pattern(ENTITIES[code]), "", remaining, flags=re.I)
    remaining = remaining.strip(" 的，,。 ") or None
    return {"entities": applied, "ranking_query": remaining,
            "reasons": [f"{code}: explicit query term supported by final reviewed case text/tags" for code in applied]
            + [f"{code}: no confident reviewed entity evidence; retained in ranking query" for code in recognized if code not in available]}

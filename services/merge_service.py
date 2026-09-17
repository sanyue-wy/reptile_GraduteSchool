"""Record-oriented adapter around the existing grouped merge algorithm."""
from copy import deepcopy
import difflib
from pipelines.merge import match_records, merge_pair, normalize_name, strip_name


class MergeService:
    def __init__(self, fuzzy_threshold=0.85):
        self.fuzzy_threshold = fuzzy_threshold

    def match_records(self, a, b):
        if any(a.get(k, "") != b.get(k, "") for k in ("university", "college")):
            return False, "none"
        left, right = normalize_name(a.get("name", "")), normalize_name(b.get("name", ""))
        if not left or not right:
            return False, "none"
        if left == right:
            return True, "exact"
        left, right = strip_name(left), strip_name(right)
        if left == right:
            return True, "strip"
        if difflib.get_close_matches(left, [right], n=1, cutoff=self.fuzzy_threshold):
            return True, "fuzzy"
        return False, "none"

    def merge_sources(self, faculty_records, notice_records):
        pairs, _, _ = match_records(faculty_records, notice_records, self.fuzzy_threshold)
        return deepcopy([merge_pair(a, b, status) for a, b, status in pairs])

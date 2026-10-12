"""Checks for review.py that need no network: the recommended actions as cards, and the document around them."""

import re
import sys
import unittest
from pathlib import Path
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parent))
import review  # noqa: E402

LESSON = {"id": "route-conflicting-pr", "lever": "autonomy", "day": "2026-10-11", "state": "proposed",
          "title": "Send a conflicting PR to the implementer", "where": "ub-agents launcher",
          "change": "Hand an approved CONFLICTING PR to the implementer's base-merge repair.",
          "cost": "5 integrator runs on 11 October", "causes": ["main-moved-under-ready-pr"], "evidence": [1212, 1394]}


class Tests(unittest.TestCase):
    def test_action_card(self):
        card = review.action_card("o/r", "2026-10-11", LESSON)
        self.assertEqual(card["type"], "card")
        self.assertEqual(card["text"], "label: More autonomy\ntitle: Send a conflicting PR to the implementer\n"
                                       "footer: ub-agents launcher · 5 integrator runs on 11 October · "
                                       "main-moved-under-ready-pr · [#1212](https://github.com/o/r/issues/1212) "
                                       "[#1394](https://github.com/o/r/issues/1394)\n\n"
                                       "Hand an approved CONFLICTING PR to the implementer's base-merge repair.",
                         "the footer carries the evidence; no button unless asked for")
        bare = {k: LESSON[k] for k in ("lever", "title", "change")}
        self.assertNotIn("footer:", review.action_card("o/r", "2026-10-11", bare)["text"], "no evidence, no footer")

    def test_button_prompt(self):
        head = review.action_card("o/r", "2026-10-11", LESSON, doc="d0c", button=True)["text"].partition("\n\n")[0]
        button = head.split("\n")[-1]
        self.assertTrue(button.startswith("button: [Discuss in Claude Code](claude://code/new?q="), "after the footer")
        prompt = unquote(re.search(r"q=(\S+)\)$", button).group(1))
        for part in ("delivery report for o/r (Uberblick document d0c), data as of 2026-10-11",
                     "Recommendation: Send a conflicting PR to the implementer.", "Where: ub-agents launcher",
                     "Evidence: #1212, #1394", "never add a role, label, gate", "wait for my go-ahead"):
            self.assertIn(part, prompt)

    def test_document_ranks_current_actions(self):
        old = dict(LESSON, title="Old lesson", day="2026-09-01")
        done = dict(LESSON, title="Done lesson", state="applied")
        dataset = {"lessons": [{"id": "a", "value": LESSON}, {"id": "old", "value": old},
                               {"id": "done", "value": done}], "changes": []}
        data = {"repo": "o/r", "day": "2026-10-11", "lessons": [], "changes": [], "actions": ["done", "old", "a"]}
        actions = review.document(dataset, data)["actions"]
        self.assertTrue(actions[0]["text"].startswith("Up to five changes"))
        self.assertEqual([b["type"] for b in actions], ["paragraph", "card"], "only proposed lessons from 14 days")
        created = review.create_document(dict(data, summary={}))
        headings = [b["text"] for b in created["blocks"] if b["type"] == "heading"]
        self.assertIn("Recommended Actions", headings)
        self.assertLess(headings.index("Recommended Actions"), headings.index("Changelog"))


if __name__ == "__main__":
    unittest.main()

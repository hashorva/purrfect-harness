import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import observe_output as O


def figures(name):
    raw = (ROOT / "tests/fixtures/observe" / f"tokens-{name}.jsonl").read_bytes()
    result = O.token_figures(name, raw)
    return {key: result[key]["value"] for key in O.TOKEN_FIGURE_FIELDS}


class TokenFigures(unittest.TestCase):
    def test_claude(self):
        self.assertEqual(figures("claude"), dict(input=46, output=15715, reasoning=5122, cache_read=1683716,
                                                  cache_write=72207, total=1771684, without_cache=87968))

    def test_codex(self):
        self.assertEqual(figures("codex"), dict(input=1154574, output=10368, reasoning=2321, cache_read=1078784,
                                                 cache_write=0, total=1164942, without_cache=86158))

    def test_cursor(self):
        self.assertEqual(figures("cursor"), dict(input=39280, output=5387, reasoning=None, cache_read=233463,
                                                  cache_write=0, total=278130, without_cache=44667))
        self.assertEqual(O.token_figures("agent", b"")["total"], O.unknown())

    def test_agy(self):
        self.assertEqual(figures("agy"), dict(input=3216, output=202, reasoning=126, cache_read=16873,
                                               cache_write=None, total=20291, without_cache=3418))

    def test_unproven_totals_are_unknown(self):
        codex = json.loads((ROOT / "tests/fixtures/observe/tokens-codex.jsonl").read_text().splitlines()[0])
        codex["usage"]["cache_write_input_tokens"] = 5
        agy = json.loads((ROOT / "tests/fixtures/observe/tokens-agy.jsonl").read_text())
        agy["result"]["usage"]["total_tokens"] = 9999
        cursor = json.loads((ROOT / "tests/fixtures/observe/tokens-cursor.jsonl").read_text())
        del cursor["usage"]["cacheWriteTokens"]
        cases = (("codex", codex), ("agy", agy), ("cursor", cursor))
        for provider, event in cases:
            with self.subTest(provider=provider):
                data = (json.dumps(event) + "\n").encode()
                result = O.token_figures(provider, data)
                self.assertEqual(result["total"], O.unknown())
                self.assertEqual(result["without_cache"], O.unknown())
        self.assertTrue(all(value == O.unknown() for value in O.token_figures("claude", b"").values()))


if __name__ == "__main__":
    unittest.main()

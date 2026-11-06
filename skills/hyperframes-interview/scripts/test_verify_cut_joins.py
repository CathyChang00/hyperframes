#!/usr/bin/env python3
"""Run: python3 scripts/test_verify_cut_joins.py (no ASR server; a fake transcriber reads a word map)."""
import unittest

import numpy as np

import verify_cut_joins as vj

SR = 16000


class JoinChecks(unittest.TestCase):
    def setUp(self):
        # 1 s silence, then words as 0.3 s tones: "keep this", 0.4 s pause (1.65-2.05), "drop that", 0.4 s pause (2.70-3.10), "keep more"
        layout = [('keep', 0.05), ('this', 0.4), ('drop', 0.05), ('that', 0.4), ('keep', 0.05), ('more', 1.0)]
        audio, self.words, t = [np.full(SR, 1e-4, np.float32)], [], 1.0
        tone = (0.2 * np.sin(2 * np.pi * 220 * np.arange(int(0.3 * SR)) / SR)).astype(np.float32)
        for word, gap in layout:
            audio += [tone, np.full(int(gap * SR), 1e-4, np.float32)]
            self.words.append((t, t + 0.3, word))
            t += 0.3 + gap
        self.db = vj.envelope(np.concatenate(audio), SR)

    def transcribe(self, ranges):
        # a word is heard when at least 50 ms of it lies inside a range
        return ' '.join(w for a, b in ranges for s, e, w in self.words if min(e, b) - max(s, a) > 0.05)

    def test_quiet_runs_find_the_word_gaps(self):
        long_runs = [(a, b) for a, b in vj.quiet_runs(self.db, 1.0, 4.0) if b - a > 0.3]
        self.assertEqual(len(long_runs), 2)
        self.assertAlmostEqual(long_runs[0][0], 1.65, delta=0.03)
        self.assertAlmostEqual(long_runs[1][0], 2.70, delta=0.03)

    def test_two_sided_match_cuts_inside_both_pauses(self):
        j = dict(id='T', est_in=1.7, est_out=2.9, keep_tail='keep this', drop_head='drop',
                 drop_tail='drop that', keep_head='keep more')
        rec = vj.solve(j, self.transcribe, self.db, 30.0)
        self.assertTrue(rec['ok'], rec)
        self.assertTrue(1.65 <= rec['frame_in'] / 30 <= 2.05)
        self.assertTrue(2.70 <= rec["frame_out"] / 30 <= 3.10)
        self.assertEqual(rec['joined_text'], 'keep this keep more')

    def test_wrong_expectation_is_rejected_not_forced(self):
        j = dict(id='T', est_in=1.7, est_out=2.9, keep_tail='keep this', drop_head='something else',
                 drop_tail='drop that', keep_head='keep more')
        self.assertFalse(vj.solve(j, self.transcribe, self.db, 30.0)['ok'])

    def test_phrase_helpers(self):
        self.assertTrue(vj.ends_with(vj.norm('...before you drop out.'), 'drop out'))
        self.assertTrue(vj.starts_with(vj.norm("I don't think my"), "i don't think"))
        self.assertFalse(vj.starts_with(vj.norm('For early online'), 'why'))


if __name__ == '__main__':
    unittest.main()

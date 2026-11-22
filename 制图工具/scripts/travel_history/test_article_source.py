"""Regression checks for the article as the only editable railway timetable."""
import unittest
from parse_source import parse_rail_records, read_rail_records, DEFAULT_POST


class ArticleTimetableTests(unittest.TestCase):
    def parse(self, rows):
        return parse_rail_records([
            "{% hideToggle 展开铁路记录表 %}",
            "|日期|出发地|目的地|车次|里程（km）|时间|备注|",
            "|:---:|:---:|:---:|:---:|:---:|:---:|:---:|",
            *rows, "{% endhideToggle %}",
        ])

    def test_complete_rows_keep_clocks_with_their_routes(self):
        records = self.parse([
            "|2027.1.1|北京南|天津|C1234|120|08:00-09:00|备注一|",
            "|2027.1.1|天津|北京南|C1235|120|19:00-20:00|备注二|",
        ])
        self.assertEqual(records[1]["time"], "19:00-20:00")
        self.assertEqual(records[1]["note"], "备注二")
        self.assertEqual(records[1]["origin"], "天津")

    def test_malformed_row_fails_instead_of_shifting_later_fields(self):
        with self.assertRaises(ValueError):
            self.parse(["|2027.1.1|北京南|天津|C1234|120|08:00-09:00|"])

    def test_current_article_has_complete_timetable_and_correct_direction(self):
        records = read_rail_records(DEFAULT_POST)
        self.assertEqual(len(records), 150)
        self.assertEqual(sum(r["distance_km"] for r in records), 63248)
        self.assertEqual((records[10]["origin"], records[10]["destination"]), ("广州南", "湛江西"))
        self.assertEqual(records[104]["time"], "11:37-19:03")
        self.assertEqual(records[106]["date"], "2026.4.19")
        self.assertEqual(
            tuple(records[148][field] for field in ("date", "origin", "destination", "train", "distance_km", "time")),
            ("2026.11.21", "北京西", "大兴机场", "G8851", 47, "7:31-8:00"),
        )
        self.assertEqual(
            tuple(records[149][field] for field in ("date", "origin", "destination", "train", "distance_km", "time", "note")),
            ("2026.11.23", "东营", "北京丰台", "K1786", 535, "8:07-15:10", ""),
        )


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import fakeredis

from datamingler.engine import QueryEvaluator
from datamingler.kvstore import KeyListStore
from datamingler.sources import DataSourceRegistry
from datamingler.xmlio import load_dvm_xml, load_query_text, parse_query_text, save_query_xml, load_query_xml


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


def _make_store() -> KeyListStore:
    """Return a KeyListStore backed by fakeredis (no live Redis needed in tests)."""
    store = object.__new__(KeyListStore)
    store._redis = fakeredis.FakeRedis(decode_responses=True)
    return store


class DataMinglerCoreTests(unittest.TestCase):
    def test_text_query_round_trip(self) -> None:
        plan = parse_query_text((EXAMPLES / "customer_summary.qdvm").read_text(encoding="utf-8"))
        self.assertEqual(plan.root, "X")
        self.assertEqual(plan.nodes["X"].children, ("A", "G", "N"))
        self.assertTrue(plan.nodes["A"].output)
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "query.xml"
            save_query_xml(plan, path)
            loaded = load_query_xml(path)
        self.assertEqual(loaded.root, plan.root)
        self.assertEqual(loaded.nodes["N"].transformations[0].name, "map")

    def test_customer_summary_evaluation(self) -> None:
        graph = load_dvm_xml(EXAMPLES / "sample.dvm.xml")
        registry = DataSourceRegistry.from_xml(EXAMPLES / "datasources.xml")
        plan = load_query_text(EXAMPLES / "customer_summary.qdvm")
        result = QueryEvaluator(graph, registry, store=_make_store()).evaluate(plan)
        rows = {row["custID-X"]: row for row in result.to_rows()}
        self.assertEqual(rows["C1"]["Age-A"], "35")
        self.assertEqual(rows["C1"]["Gender-G"], "F")
        self.assertEqual(rows["C1"]["Comment-N"], "10.0")
        self.assertEqual(rows["C2"]["Comment-N"], "3.0")

    def test_nested_theta_json_evaluation(self) -> None:
        graph = load_dvm_xml(EXAMPLES / "sample.dvm.xml")
        registry = DataSourceRegistry.from_xml(EXAMPLES / "datasources.xml")
        plan = load_query_text(EXAMPLES / "transactions_after_2019.qdvm")
        result = QueryEvaluator(graph, registry, store=_make_store()).evaluate(plan)
        records = {record["custID-X"]: record for record in result.to_json_records()}
        self.assertEqual(records["C1"]["transID-T_s"], [{"transID-T": "T1", "Amount-Amt": "10"}])
        self.assertEqual(records["C2"]["transID-T_s"], [{"transID-T": "T3", "Amount-Amt": "5"}])


if __name__ == "__main__":
    unittest.main()

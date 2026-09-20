"""Read an NUnit test-results.xml and report counts from the XML, never from console text.

Usage: python check_recheck_xml.py <xml path> <expected total>
Exit 0 only when total == expected and failed == 0. A run that selects zero tests reports
total=0 and exits 0 in raw Unity; that is a failure here, not a pass.
"""
import sys
import xml.etree.ElementTree as ET

path = sys.argv[1]
expected_total = sys.argv[2]

root = ET.parse(path).getroot()
counts = {k: root.get(k) for k in ("total", "passed", "failed", "skipped", "result")}
types = sorted({(tc.get("classname") or tc.get("fullname", "").rsplit(".", 1)[0])
                for tc in root.iter("test-case")})
print("  counts:", counts)
print("  declaring types:", types)

ok = counts["total"] == expected_total and counts["failed"] == "0"
print("  VERDICT:", "PASS" if ok else "FAIL (expected total=%s failed=0)" % expected_total)
sys.exit(0 if ok else 1)

import sys,os
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server

G="(01)09506000134352(21)SER123"
def test_parse():
    assert server.parse_gs1(G).gtin=="09506000134352"
def test_govern():
    assert any("Digital Product Passport" in f for f in server.govern_traceability(G).frameworks)

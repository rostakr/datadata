from __future__ import annotations

from tools.a6_viewport_smoke import EXPECTED_TABS, VIEWPORTS


def test_viewport_matrix_covers_desktop_and_iphone_orientations():
    cases = {case.name: (case.width, case.height) for case in VIEWPORTS}

    assert cases["desktop"] == (1440, 900)
    assert cases["iphone-portrait"] == (390, 844)
    assert cases["iphone-landscape"] == (844, 390)
    assert cases["iphone-portrait"][0] < cases["iphone-portrait"][1]
    assert cases["iphone-landscape"][0] > cases["iphone-landscape"][1]


def test_viewport_smoke_requires_all_primary_a6_tabs():
    assert EXPECTED_TABS == [
        "Konverzace",
        "Časová osa",
        "Grafy",
        "Významná období",
        "Lexikální témata",
        "Vybrané zprávy",
        "Analýza",
    ]

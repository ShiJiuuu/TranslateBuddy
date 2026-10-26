from backend.glossary import Glossary


def test_lock_and_unlock():
    glossary = Glossary({"Revenue": "营收", "enterprise segment": "企业客户"})
    locked, mapping = glossary.lock("Revenue grew, enterprise segment strong")

    assert "Revenue" not in locked
    assert "enterprise segment" not in locked
    assert set(mapping.values()) == {"营收", "企业客户"}

    restored, missing = glossary.unlock(locked, mapping)
    assert "营收" in restored
    assert "企业客户" in restored
    assert missing == []


def test_missing_placeholder_is_reported():
    glossary = Glossary({"Revenue": "营收"})
    _, mapping = glossary.lock("Revenue")
    restored, missing = glossary.unlock("翻掉了占位符", mapping)
    assert missing == ["营收"]
    assert restored == "翻掉了占位符"  # 不吞掉译文


def test_empty_glossary_is_falsy():
    assert not Glossary({})

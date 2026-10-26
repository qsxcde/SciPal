"""配置文档完整性：新增字段必须写进 wiki 08。"""

import pytest

from backend.config import RuntimeSettings
from backend.scripts.config_doc import doc_path, missing_fields


@pytest.mark.unit
def test_every_setting_is_documented():
    text = doc_path().read_text(encoding="utf-8")
    missing = missing_fields(text, list(RuntimeSettings.model_fields))

    assert missing == [], f"以下配置未写入 docs/wiki/08-configuration.md: {missing}"

from __future__ import annotations

import importlib
import os
import sys
import unittest
from unittest.mock import patch

import dotenv


class ConfigTests(unittest.TestCase):
    def test_default_alert_rescrape_interval_is_three_hours(self):
        original_config = sys.modules.pop("config", None)
        try:
            with patch.object(dotenv, "load_dotenv"), patch.dict(os.environ, {}, clear=True):
                config = importlib.import_module("config")
            self.assertEqual(config.ALERT_RESCRAPE_INTERVAL_SECONDS, 3 * 3600)
        finally:
            sys.modules.pop("config", None)
            if original_config is not None:
                sys.modules["config"] = original_config


if __name__ == "__main__":
    unittest.main()

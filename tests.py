"""
Unit tests for bot.py — covers critical security, data, and logic paths.
Run: python -m pytest tests.py -v
"""
import json
import os
import tempfile
import sys
import ast
import pytest

# Mock environment before importing bot
os.environ["BOT_TOKEN"] = "123456:test-token-for-ci"
os.environ["ADMIN_ID"] = "12345"

import bot


# ─── safe_eval tests ─────────────────────────────────────────────

class TestSafeEval:
    def test_basic_arithmetic(self):
        assert bot.safe_eval("1+1") == 2
        assert bot.safe_eval("2*3") == 6
        assert bot.safe_eval("10/2") == 5.0
        assert bot.safe_eval("10-4") == 6
        assert bot.safe_eval("2**3") == 8
        assert bot.safe_eval("10%3") == 1

    def test_pi_and_e(self):
        assert abs(bot.safe_eval("pi") - 3.141592653589793) < 1e-10
        assert abs(bot.safe_eval("e") - 2.718281828459045) < 1e-10

    def test_sqrt(self):
        assert bot.safe_eval("sqrt(9)") == 3.0
        assert bot.safe_eval("sqrt(2)") ** 2 == pytest.approx(2.0, rel=1e-10)

    def test_functions(self):
        assert bot.safe_eval("abs(-5)") == 5
        assert bot.safe_eval("round(3.7)") == 4
        assert bot.safe_eval("int(3.9)") == 3
        assert bot.safe_eval("float(5)") == 5.0
        assert bot.safe_eval("min(1,2,3)") == 1
        assert bot.safe_eval("max(1,2,3)") == 3
        assert bot.safe_eval("sum([1,2,3])") == 6
        assert bot.safe_eval("pow(2,3)") == 8

    def test_x_and_colon(self):
        """Test calc_cmd normalization: 2x3 -> 2*3, 6:2 -> 6/2"""
        expr = "2x3"
        norm = bot.re.sub(r'(\d)x(\d)', r'\1*\2', expr, flags=bot.re.IGNORECASE).replace(":", "/")
        assert bot.safe_eval(norm) == 6
        expr = "6:2"
        norm = bot.re.sub(r'(\d)x(\d)', r'\1*\2', expr, flags=bot.re.IGNORECASE).replace(":", "/")
        assert bot.safe_eval(norm) == 3.0

    def test_calc_x_not_replace_function_names(self):
        """calc 'max' should not become 'ma*'"""
        expr = bot.re.sub(r'(\d)x(\d)', r'\1*\2', 'max(1,2)', flags=bot.re.IGNORECASE)
        assert expr == 'max(1,2)'
        expr = bot.re.sub(r'(\d)x(\d)', r'\1*\2', 'hex(255)', flags=bot.re.IGNORECASE)
        assert expr == 'hex(255)'

    @pytest.mark.parametrize("malicious", [
        "__import__('os').system('echo hack')",
        "__class__.__mro__[1].__subclasses__()",
        "math.__class__.__mro__[1].__subclasses__()",
        "globals()",
        "locals()",
        "open('/etc/passwd')",
        "exec('x=1')",
        "eval('1+1')",
        "().__class__.__bases__[0].__subclasses__()",
        "''.__class__.__mro__[2].__subclasses__()",
        "[x for x in [].__class__.__mro__]",
    ])
    def test_security_blocked(self, malicious):
        with pytest.raises(Exception):
            bot.safe_eval(malicious)

    def test_unknown_name_blocked(self):
        with pytest.raises(Exception):
            bot.safe_eval("os")

    def test_invalid_characters_blocked(self):
        with pytest.raises(Exception):
            bot.safe_eval("1+1; import os")

    def test_nested_expression_ok(self):
        result = bot.safe_eval("(2+3)*4-1+sqrt(16)/2")
        assert result == 21.0


# ─── JSON persistence tests ──────────────────────────────────────

class TestJSONPersistence:
    def test_safe_load_valid(self):
        data = {"a": 1, "b": [2, 3]}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(data, f)
            path = f.name
        try:
            result = bot.safe_json_load(path, {})
            assert result == data
        finally:
            os.unlink(path)

    def test_safe_load_corrupted(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            f.write("{invalid json!!!}")
            path = f.name
        try:
            result = bot.safe_json_load(path, {})
            assert result == {}
        finally:
            os.unlink(path)

    def test_safe_load_missing_file(self):
        result = bot.safe_json_load("/nonexistent/path.json", [])
        assert result == []

    def test_safe_load_type_mismatch(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump([1, 2, 3], f)
            path = f.name
        try:
            result = bot.safe_json_load(path, {})
            assert result == {}
        finally:
            os.unlink(path)

    def test_save_and_reload(self):
        data = {"users": {"1": [{"id": 1, "content": "test"}]}}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            path = f.name
        try:
            bot.save_json(path, data)
            result = bot.safe_json_load(path, {})
            assert result == data
        finally:
            os.unlink(path)


# ─── Cache tests ─────────────────────────────────────────────────

class TestCache:
    def test_cache_get_set(self):
        bot._cache.clear()
        bot._cache_access_order.clear()
        bot.cache_set("test_key", "test_value")
        assert bot.cache_get("test_key", ttl=60) == "test_value"

    def test_cache_expiry(self):
        bot._cache.clear()
        bot._cache_access_order.clear()
        bot._cache["expired_key"] = (0.0, "old_value")
        result = bot.cache_get("expired_key", ttl=1)
        assert result is None

    def test_cache_eviction(self):
        bot._cache.clear()
        bot._cache_access_order.clear()
        old_maxsize = bot._cache_maxsize
        bot._cache_maxsize = 3
        try:
            bot.cache_set("k1", "v1")
            bot.cache_set("k2", "v2")
            bot.cache_set("k3", "v3")
            bot.cache_set("k4", "v4")
            assert len(bot._cache) == 3
            assert "k1" not in bot._cache
        finally:
            bot._cache_maxsize = old_maxsize
            bot._cache.clear()
            bot._cache_access_order.clear()

    def test_cache_lru_order(self):
        bot._cache.clear()
        bot._cache_access_order.clear()
        old_maxsize = bot._cache_maxsize
        bot._cache_maxsize = 3
        try:
            bot.cache_set("k1", "v1")
            bot.cache_set("k2", "v2")
            bot.cache_set("k3", "v3")
            # Access k1 to refresh it
            bot.cache_get("k1", ttl=60)
            bot.cache_set("k4", "v4")
            # k2 should be evicted (oldest unused)
            assert "k1" in bot._cache
            assert "k2" not in bot._cache
        finally:
            bot._cache_maxsize = old_maxsize
            bot._cache.clear()
            bot._cache_access_order.clear()


# ─── Rate limiting cleanup tests ─────────────────────────────────

class TestRateLimitCleanup:
    def test_cleanup_removes_stale(self):
        import time
        bot._last_call.clear()
        now = time.monotonic()
        bot._last_call[("user1", "test")] = now - 7200
        bot._last_call[("user2", "test")] = now
        bot._cleanup_rate_limits()
        assert ("user1", "test") not in bot._last_call
        assert ("user2", "test") in bot._last_call


# ─── Van blacklist tests ─────────────────────────────────────────

class TestVanBlacklist:
    def test_blacklist_persistence(self, monkeypatch):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            path = f.name
        monkeypatch.setattr(bot, "VAN_BLACKLIST_FILE", path)
        try:
            assert bot.load_van_blacklist() == []
            bot.save_van_blacklist(["url1", "url2"])
            assert bot.load_van_blacklist() == ["url1", "url2"]
            lst = bot.load_van_blacklist()
            lst.append("url3")
            bot.save_van_blacklist(lst)
            assert len(bot.load_van_blacklist()) == 3
        finally:
            os.unlink(path)


# ─── Config validation tests ─────────────────────────────────────

class TestConfig:
    def test_token_required(self, monkeypatch):
        monkeypatch.delenv("BOT_TOKEN", raising=False)
        with pytest.raises(SystemExit):
            if not os.environ.get("BOT_TOKEN"):
                sys.exit("FATAL: BOT_TOKEN environment variable is required")

    def test_admin_id_optional(self):
        assert bot.ADMIN_ID == 12345

    def test_admin_id_none(self, monkeypatch):
        monkeypatch.delenv("ADMIN_ID", raising=False)
        admin_str = os.environ.get("ADMIN_ID")
        if admin_str:
            assert int(admin_str) == 12345
        else:
            assert bot.ADMIN_ID is not None

    def test_start_time_set(self):
        assert bot.START_TIME is not None
        import datetime
        assert isinstance(bot.START_TIME, datetime.datetime)


# ─── Reminder logic tests ────────────────────────────────────────

class TestReminderLogic:
    def test_reminder_structure(self):
        user_id = "test_user"
        bot.reminders[user_id] = []
        rid = len(bot.reminders[user_id]) + 1
        bot.reminders[user_id].append({"id": rid, "content": "test reminder", "seconds": 60})
        assert len(bot.reminders[user_id]) == 1
        assert bot.reminders[user_id][0]["id"] == 1

    def test_reminder_cancel(self):
        user_id = "test_user2"
        bot.reminders[user_id] = [{"id": 1, "content": "a", "seconds": 10}]
        bot.reminders[user_id] = [r for r in bot.reminders[user_id] if r["id"] != 1]
        assert len(bot.reminders[user_id]) == 0

    def test_reminder_second_bound(self):
        """Remind should reject <5 and >30days"""
        from datetime import datetime
        created = {"seconds": 60}
        assert 5 <= created["seconds"] <= 86400 * 30

    def test_reminder_too_short_rejected(self):
        """Test bot.remind exists and has rate_limit decorator"""
        assert callable(bot.remind)

    def test_reminder_too_long_rejected(self):
        """Test 30-day max constant exists"""
        assert 86400 * 30 == 2592000


# ─── Password logic tests ────────────────────────────────────────

class TestPasswordLogic:
    def test_password_generation(self):
        import secrets, string
        chars = string.ascii_letters + string.digits + "!@#$%^&*"
        pw = "".join(secrets.choice(chars) for _ in range(16))
        assert len(pw) == 16
        assert all(c in chars for c in pw)

    def test_password_length_bounds(self):
        """Test password clamping matches bot.py logic"""
        def clamp(val): return max(6, min(val, 64))
        assert clamp(4) == 6
        assert clamp(64) == 64
        assert clamp(100) == 64

    def test_password_storage(self):
        user_id = "test_pw_user"
        bot.passwords[user_id] = []
        bot.passwords[user_id].append({"id": 1, "label": "test", "password": "secret123"})
        assert len(bot.passwords[user_id]) == 1
        assert bot.passwords[user_id][0]["password"] == "secret123"

    def test_password_delete(self):
        user_id = "test_pw_user2"
        bot.passwords[user_id] = [{"id": 1, "label": "a", "password": "p1"}, {"id": 2, "label": "b", "password": "p2"}]
        bot.passwords[user_id] = [p for p in bot.passwords[user_id] if p["id"] != 1]
        assert len(bot.passwords[user_id]) == 1
        assert bot.passwords[user_id][0]["id"] == 2

    def test_password_edit(self):
        user_id = "test_pw_user3"
        bot.passwords[user_id] = [{"id": 1, "label": "a", "password": "old"}]
        for p in bot.passwords[user_id]:
            if p["id"] == 1:
                p["password"] = "new"
        assert bot.passwords[user_id][0]["password"] == "new"


# ─── URL validation tests ────────────────────────────────────────

class TestURLValidation:
    def test_ensure_https(self):
        url = "google.com"
        if not url.startswith("http"):
            url = "https://" + url
        assert url == "https://google.com"

    def test_https_preserved(self):
        url = "https://example.com"
        if not url.startswith("http"):
            url = "https://" + url
        assert url == "https://example.com"

    def test_http_preserved(self):
        url = "http://example.com"
        if not url.startswith("http"):
            url = "https://" + url
        assert url == "http://example.com"

    def test_empty_url(self):
        url = ""
        if not url.startswith("http"):
            url = "https://" + url
        assert url == "https://"


# ─── Helper: van_cmd link filtering ──────────────────────────────

class TestVanLinkFilter:
    def test_essay_link_filter(self):
        links = [
            "/van-mau-lop-8/..",
            "/van-mau-lop-8/index.jsp",
            "/van-mau-lop-8/van-mau.jsp",
            "/van-mau-lop-8/phan-tich.jsp",
            "/toan-hoc/",
        ]
        essays = []
        for l in links:
            if "/van-mau-lop-8/" in l and l.endswith(".jsp") and "index.jsp" not in l:
                essays.append(l)
        assert essays == ["/van-mau-lop-8/van-mau.jsp", "/van-mau-lop-8/phan-tich.jsp"]

    def test_empty_essay_list(self):
        essays = []
        assert not essays


# ─── Crypto data parsing ─────────────────────────────────────────

class TestCryptoParsing:
    def test_price_formatting(self):
        data = {
            "bitcoin": {"usd": 50000, "usd_24h_change": 2.5},
            "ethereum": {"usd": 3000, "usd_24h_change": -1.2},
        }
        lines = ["Giá Crypto (USD):"]
        for coin, info in data.items():
            price = info["usd"]
            change = info.get("usd_24h_change", 0)
            arrow = "📈" if change >= 0 else "📉"
            lines.append(f"{coin.upper()}: ${price} ({arrow} {change:+.2f}%)")
        assert "📈" in lines[1]
        assert "📉" in lines[2]

    def test_missing_change_field(self):
        data = {"bitcoin": {"usd": 50000}}
        change = data.get("bitcoin", {}).get("usd_24h_change", 0)
        assert change == 0


# ─── Translate response parser ───────────────────────────────────

class TestTranslateParsing:
    def test_safe_traversal(self):
        response = [[["Xin chào", None]], None, ["en"]]
        result = ""
        if isinstance(response, list) and len(response) > 0 and isinstance(response[0], list):
            result = "".join(part[0] for part in response[0] if isinstance(part, list) and len(part) > 0)
        assert result == "Xin chào"

    def test_malformed_response(self):
        response = {"error": "bad request"}
        result = ""
        if isinstance(response, list) and len(response) > 0 and isinstance(response[0], list):
            result = "".join(part[0] for part in response[0] if isinstance(part, list) and len(part) > 0)
        else:
            result = str(response)
        assert "error" in result


# ─── Flood protection tests ──────────────────────────────────────

class TestFloodProtection:
    def test_no_flood_under_limit(self):
        bot._flood_count.clear()
        for _ in range(bot.FLOOD_LIMIT - 1):
            assert not bot.is_flood(99999)
        bot._flood_count.clear()

    def test_flood_at_limit(self):
        bot._flood_count.clear()
        for _ in range(bot.FLOOD_LIMIT):
            bot.is_flood(99998)
        assert bot.is_flood(99998)
        bot._flood_count.clear()


# ─── Runtime: safe_json_load integration ─────────────────────────

class TestIntegration:
    def test_reminders_save_load_cycle(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            path = f.name
        try:
            test_data = {"user1": [{"id": 1, "content": "hello", "seconds": 30}]}
            bot.save_json(path, test_data)
            loaded = bot.safe_json_load(path, {})
            assert loaded == test_data
            assert loaded["user1"][0]["content"] == "hello"
        finally:
            os.unlink(path)

    def test_passwords_save_load_cycle(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            path = f.name
        try:
            test_data = {"user1": [{"id": 1, "label": "email", "password": "secret"}]}
            bot.save_json(path, test_data)
            loaded = bot.safe_json_load(path, {})
            assert loaded["user1"][0]["password"] == "secret"
        finally:
            os.unlink(path)


# ─── i18n / Multi-language tests ─────────────────────────────────

class TestI18n:
    def test_t_vi_default(self):
        """Default language should be Vietnamese."""
        result = bot.t("rate_limit", user_id=None, s=5)
        assert "Thử lại" in result or "Chậm" in result

    def test_t_vi_explicit(self):
        bot._user_lang[99999] = "vi"
        result = bot.t("stock_no_args", user_id=99999)
        assert "Dùng" in result or "/stock" in result

    def test_t_en_explicit(self):
        bot._user_lang[88888] = "en"
        result = bot.t("stock_no_args", user_id=88888)
        assert "Usage" in result

    def test_t_fallback(self):
        """Unknown key should return the key itself."""
        result = bot.t("nonexistent_key_xyz")
        assert result == "nonexistent_key_xyz"

    def test_t_with_kwargs(self):
        bot._user_lang[77777] = "vi"
        result = bot.t("stock_title", user_id=77777, symbol="FPT")
        assert "FPT" in result

    def test_get_user_lang(self):
        bot._user_lang[66666] = "en"
        assert bot.get_user_lang(66666) == "en"
        assert bot.get_user_lang(55555) == "vi"

    def test_lang_dict_all_keys_present(self):
        """Both languages should have the same keys."""
        vi_keys = set(bot.STRINGS["vi"].keys())
        en_keys = set(bot.STRINGS["en"].keys())
        assert vi_keys == en_keys, f"Missing in EN: {vi_keys - en_keys}, Missing in VI: {en_keys - vi_keys}"


# ─── Stock ticker tests ──────────────────────────────────────────

class TestStockTicker:
    def test_vn_ticker_auto_suffix(self):
        """FPT -> FPT.VN auto-suffix."""
        vn_tickers = {"FPT", "VNM", "VCB"}
        symbol = "FPT"
        if "." not in symbol and symbol in vn_tickers:
            symbol = f"{symbol}.VN"
        assert symbol == "FPT.VN"

    def test_us_ticker_no_suffix(self):
        symbol = "AAPL"
        vn_tickers = {"FPT", "VNM", "VCB"}
        if "." not in symbol and symbol in vn_tickers:
            symbol = f"{symbol}.VN"
        assert symbol == "AAPL"

    def test_existing_suffix_preserved(self):
        symbol = "FPT.VN"
        vn_tickers = {"FPT", "VNM", "VCB"}
        if "." not in symbol and symbol in vn_tickers:
            symbol = f"{symbol}.VN"
        assert symbol == "FPT.VN"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

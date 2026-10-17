"""LeehExchange Rewards domain service.

The bot and Flask admin app share this module.  Existing users remain in
``user_data.json`` and existing orders remain in ``transactions.csv``;
``rewards_data.json`` only stores the auditable points/rewards ledger and
configuration needed by the new feature.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import uuid
from collections import defaultdict
from datetime import datetime
from typing import Any, Callable

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows development fallback
    fcntl = None


REWARDS_DATA_FILE = "rewards_data.json"
USER_DATA_FILE = "user_data.json"
COMPLETED_STATUSES = {"approved", "completed"}

DEFAULT_ACTIONS = {
    "account_registration": {
        "label": "Create a LeehExchange account",
        "description": "Join the bot and complete registration.",
        "points": 25,
        "enabled": True,
        "once": True,
    },
    "first_successful_trade": {
        "label": "Complete your first successful trade",
        "description": "Your first approved or completed order.",
        "points": 100,
        "enabled": True,
        "once": True,
    },
    "completed_trade": {
        "label": "Complete a trade",
        "description": "Earn points after each approved or completed order.",
        "points": 25,
        "enabled": True,
        "once": False,
        "daily_limit": 10,
    },
    "trading_volume_100": {
        "label": "Reach 100 in trading volume",
        "description": "Reach the configured numeric volume milestone.",
        "points": 50,
        "enabled": True,
        "once": True,
        "threshold": 100,
    },
    "trading_volume_500": {
        "label": "Reach 500 in trading volume",
        "description": "Reach the configured numeric volume milestone.",
        "points": 150,
        "enabled": True,
        "once": True,
        "threshold": 500,
    },
    "multiple_trades_5": {
        "label": "Complete 5 successful trades",
        "description": "Build a verified trading streak.",
        "points": 100,
        "enabled": True,
        "once": True,
        "threshold": 5,
    },
    "consistent_activity_7": {
        "label": "Trade on 7 different days",
        "description": "Stay active across seven verified trading days.",
        "points": 150,
        "enabled": True,
        "once": True,
        "threshold": 7,
    },
    "referral_qualifying": {
        "label": "Refer a user who completes a trade",
        "description": "Your referred friend must complete a verified transaction.",
        "points": 150,
        "enabled": True,
        "once": True,
    },
    "daily_checkin": {
        "label": "Daily reward check-in",
        "description": "Check in once every 24 hours.",
        "points": 50,
        "enabled": True,
        "once": False,
        "daily_limit": 1,
    },
    "prediction_win": {
        "label": "Win a BTC prediction",
        "description": "Earn points for a verified game result.",
        "points": 20,
        "enabled": True,
        "once": False,
        "daily_limit": 10,
    },
}

DEFAULT_DATA = {
    "version": 1,
    "settings": {
        "levels": [
            {"name": "Starter", "min_points": 0},
            {"name": "Active", "min_points": 250},
            {"name": "Pro", "min_points": 1000},
            {"name": "Elite", "min_points": 3000},
        ],
        "actions": DEFAULT_ACTIONS,
        "campaigns": [],
    },
    "accounts": {},
    "ledger": [],
    "rewards": [],
    "redemptions": [],
    "audit": [],
}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _deep_copy(value: Any) -> Any:
    return json.loads(json.dumps(value))


def _ensure_schema(data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        data = {}
    for key, default in DEFAULT_DATA.items():
        if key not in data or not isinstance(data[key], type(default)):
            data[key] = _deep_copy(default)
    settings = data["settings"]
    settings.setdefault("levels", _deep_copy(DEFAULT_DATA["settings"]["levels"]))
    settings.setdefault("actions", {})
    for key, action in DEFAULT_ACTIONS.items():
        if key not in settings["actions"]:
            settings["actions"][key] = _deep_copy(action)
        else:
            merged = _deep_copy(action)
            merged.update(settings["actions"][key])
            settings["actions"][key] = merged
    settings.setdefault("campaigns", [])
    return data


def _read_json(path: str, fallback: Any) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError, TypeError):
        return _deep_copy(fallback)


def _atomic_write(path: str, value: Any) -> None:
    directory = os.path.dirname(os.path.abspath(path)) or "."
    fd, temp_path = tempfile.mkstemp(prefix=".rewards-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def _with_lock(mutator: Callable[[dict[str, Any]], Any]) -> Any:
    lock_path = f"{REWARDS_DATA_FILE}.lock"
    os.makedirs(os.path.dirname(os.path.abspath(lock_path)) or ".", exist_ok=True)
    with open(lock_path, "a+", encoding="utf-8") as lock_handle:
        if fcntl:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        data = _ensure_schema(_read_json(REWARDS_DATA_FILE, DEFAULT_DATA))
        result = mutator(data)
        _atomic_write(REWARDS_DATA_FILE, data)
        if fcntl:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
        return result


def load_rewards_data() -> dict[str, Any]:
    return _ensure_schema(_read_json(REWARDS_DATA_FILE, DEFAULT_DATA))


def _legacy_points(user_id: str) -> int:
    user_data = _read_json(USER_DATA_FILE, {"users": {}})
    profile = user_data.get("users", {}).get(str(user_id), {})
    try:
        return max(0, int(float(profile.get("points", 0) or 0)))
    except (TypeError, ValueError):
        return 0


def _mirror_legacy_points(user_id: str, balance: int) -> None:
    """Keep old flows that read profile['points'] compatible with the ledger."""
    try:
        data = _read_json(USER_DATA_FILE, {"users": {}})
        profile = data.setdefault("users", {}).setdefault(str(user_id), {})
        profile["points"] = max(0, int(balance))
        _atomic_write(USER_DATA_FILE, data)
    except OSError:
        pass


def _account(data: dict[str, Any], user_id: str) -> dict[str, Any]:
    key = str(user_id)
    accounts = data.setdefault("accounts", {})
    if key not in accounts:
        legacy = _legacy_points(key)
        accounts[key] = {
            "balance": legacy,
            "lifetime_earned": legacy,
            "lifetime_spent": 0,
            "trade_count": 0,
            "trade_volume": 0.0,
            "trade_days": [],
            "verified_events": [],
            "qualified_referrals": 0,
            "last_activity": None,
        }
        if legacy:
            data["ledger"].append({
                "id": str(uuid.uuid4()),
                "timestamp": _now(),
                "user_id": key,
                "delta": legacy,
                "balance_after": legacy,
                "type": "legacy_import",
                "reason": "Imported existing LeehExchange points",
                "source": "migration",
                "event_key": f"legacy-import:{key}",
                "metadata": {},
            })
    account = accounts[key]
    account.setdefault("balance", 0)
    account.setdefault("lifetime_earned", max(0, int(account.get("balance", 0))))
    account.setdefault("lifetime_spent", 0)
    account.setdefault("trade_count", 0)
    account.setdefault("trade_volume", 0.0)
    account.setdefault("trade_days", [])
    account.setdefault("verified_events", [])
    account.setdefault("qualified_referrals", 0)
    account.setdefault("last_activity", None)
    return account


def _level_for(data: dict[str, Any], points: int) -> tuple[str, int | None]:
    levels = sorted(data["settings"].get("levels", []), key=lambda item: int(item.get("min_points", 0)))
    current = levels[0] if levels else {"name": "Starter", "min_points": 0}
    next_min = None
    for index, level in enumerate(levels):
        if points >= int(level.get("min_points", 0)):
            current = level
            if index + 1 < len(levels):
                next_min = int(levels[index + 1].get("min_points", 0))
    return str(current.get("name", "Starter")), next_min


def _has_event(data: dict[str, Any], event_key: str) -> bool:
    return bool(event_key) and any(item.get("event_key") == event_key for item in data["ledger"])


def _append_entry(
    data: dict[str, Any],
    user_id: str,
    delta: int,
    entry_type: str,
    reason: str,
    source: str,
    event_key: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if not delta or _has_event(data, event_key):
        return None
    account = _account(data, user_id)
    if delta < 0 and account["balance"] < abs(delta):
        return None
    account["balance"] = int(account["balance"]) + int(delta)
    if delta > 0:
        account["lifetime_earned"] = int(account["lifetime_earned"]) + int(delta)
    else:
        account["lifetime_spent"] = int(account["lifetime_spent"]) + abs(int(delta))
    account["last_activity"] = _now()
    entry = {
        "id": str(uuid.uuid4()),
        "timestamp": _now(),
        "user_id": str(user_id),
        "delta": int(delta),
        "balance_after": int(account["balance"]),
        "type": entry_type,
        "reason": reason,
        "source": source,
        "event_key": event_key,
        "metadata": metadata or {},
    }
    data["ledger"].append(entry)
    return entry


def _action_entry(
    data: dict[str, Any],
    user_id: str,
    action_key: str,
    event_key: str,
    metadata: dict[str, Any] | None = None,
    amount_override: int | None = None,
    source: str = "verified_action",
) -> dict[str, Any] | None:
    action = data["settings"]["actions"].get(action_key, {})
    if not action.get("enabled", True):
        return None
    points = int(amount_override if amount_override is not None else action.get("points", 0))
    if points <= 0 or _has_event(data, event_key):
        return None
    if action.get("once"):
        prefix = f"action:{str(user_id)}:{action_key}:"
        if any(item.get("event_key", "").startswith(prefix) for item in data["ledger"]):
            return None
    daily_limit = int(action.get("daily_limit", 0) or 0)
    if daily_limit:
        today = datetime.now().date().isoformat()
        today_count = sum(
            1 for item in data["ledger"]
            if item.get("user_id") == str(user_id)
            and item.get("source") == source
            and item.get("metadata", {}).get("action_key") == action_key
            and str(item.get("timestamp", ""))[:10] == today
            and int(item.get("delta", 0)) > 0
        )
        if today_count >= daily_limit:
            return None
    details = dict(metadata or {})
    details["action_key"] = action_key
    return _append_entry(
        data,
        str(user_id),
        points,
        "earn",
        str(action.get("label", action_key)),
        source,
        event_key,
        details,
    )


def award_action(
    user_id: int | str,
    action_key: str,
    event_key: str,
    metadata: dict[str, Any] | None = None,
    amount_override: int | None = None,
) -> dict[str, Any]:
    def mutate(data: dict[str, Any]) -> dict[str, Any]:
        entry = _action_entry(
            data, str(user_id), action_key, event_key, metadata, amount_override
        )
        account = _account(data, str(user_id))
        return {"awarded": bool(entry), "points": int(entry["delta"]) if entry else 0, "balance": int(account["balance"])}

    result = _with_lock(mutate)
    _mirror_legacy_points(str(user_id), result["balance"])
    return result


def credit_points(
    user_id: int | str,
    points: int,
    reason: str,
    event_key: str,
    source: str = "admin",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    def mutate(data: dict[str, Any]) -> dict[str, Any]:
        entry = _append_entry(data, str(user_id), abs(int(points)), "credit", reason, source, event_key, metadata)
        account = _account(data, str(user_id))
        return {"success": bool(entry), "points": abs(int(points)), "balance": int(account["balance"])}
    result = _with_lock(mutate)
    _mirror_legacy_points(str(user_id), result["balance"])
    return result


def adjust_points(
    user_id: int | str,
    delta: int,
    reason: str,
    actor: str,
    event_key: str | None = None,
) -> dict[str, Any]:
    if not str(reason).strip():
        return {"success": False, "error": "An audit reason is required"}
    key = event_key or f"manual:{uuid.uuid4()}"

    def mutate(data: dict[str, Any]) -> dict[str, Any]:
        entry = _append_entry(
            data,
            str(user_id),
            int(delta),
            "manual_adjustment",
            str(reason).strip(),
            "admin",
            key,
            {"actor": str(actor)},
        )
        account = _account(data, str(user_id))
        return {
            "success": bool(entry),
            "error": "Insufficient points" if delta < 0 and not entry else "",
            "balance": int(account["balance"]),
        }

    result = _with_lock(mutate)
    if result["success"]:
        _mirror_legacy_points(str(user_id), result["balance"])
    return result


def snapshot(user_id: int | str) -> dict[str, Any]:
    key = str(user_id)

    def mutate(data: dict[str, Any]) -> dict[str, Any]:
        account = _account(data, key)
        level, next_min = _level_for(data, int(account["lifetime_earned"]))
        return {
            "user_id": key,
            "points": int(account["balance"]),
            "lifetime_earned": int(account["lifetime_earned"]),
            "lifetime_spent": int(account["lifetime_spent"]),
            "level": level,
            "next_level_points": next_min,
            "trade_count": int(account["trade_count"]),
            "trade_volume": round(float(account["trade_volume"]), 2),
            "trade_days": len(account.get("trade_days", [])),
            "qualified_referrals": int(account.get("qualified_referrals", 0)),
        }

    result = _with_lock(mutate)
    _mirror_legacy_points(key, result["points"])
    return result


def history(user_id: int | str, limit: int = 20) -> list[dict[str, Any]]:
    data = load_rewards_data()
    rows = [row for row in data["ledger"] if row.get("user_id") == str(user_id)]
    return list(reversed(rows[-max(1, min(int(limit), 100)):]))


def leaderboard(limit: int = 10) -> list[dict[str, Any]]:
    data = load_rewards_data()
    rows = []
    for user_id, account in data["accounts"].items():
        rows.append({
            "user_id": user_id,
            "points": int(account.get("balance", 0)),
            "lifetime_earned": int(account.get("lifetime_earned", 0)),
        })
    return sorted(rows, key=lambda row: (-row["lifetime_earned"], -row["points"], row["user_id"]))[:max(1, min(int(limit), 50))]


def list_rewards(active_only: bool = False) -> list[dict[str, Any]]:
    data = load_rewards_data()
    rows = list(data.get("rewards", []))
    if active_only:
        rows = [row for row in rows if row.get("active", False)]
    return rows


def _reward_limit_hit(data: dict[str, Any], reward: dict[str, Any], user_id: str) -> str:
    now = datetime.now()
    redemptions = [
        row for row in data["redemptions"]
        if row.get("reward_id") == reward.get("id")
        and row.get("status") not in {"rejected", "cancelled"}
    ]
    inventory = int(reward.get("limit", 0) or 0)
    if inventory and len(redemptions) >= inventory:
        return "This reward has reached its claim limit."
    user_rows = [row for row in redemptions if row.get("user_id") == user_id]
    daily = int(reward.get("daily_limit", 0) or 0)
    if daily:
        count = sum(1 for row in user_rows if str(row.get("created_at", ""))[:10] == now.date().isoformat())
        if count >= daily:
            return "You have reached this reward's daily redemption limit."
    monthly = int(reward.get("monthly_limit", 0) or 0)
    if monthly:
        month = now.strftime("%Y-%m")
        count = sum(1 for row in user_rows if str(row.get("created_at", ""))[:7] == month)
        if count >= monthly:
            return "You have reached this reward's monthly redemption limit."
    return ""


def redeem_reward(user_id: int | str, reward_id: str) -> dict[str, Any]:
    key = str(user_id)

    def mutate(data: dict[str, Any]) -> dict[str, Any]:
        reward = next((row for row in data["rewards"] if row.get("id") == reward_id), None)
        if not reward or not reward.get("active"):
            return {"success": False, "error": "This reward is not available."}
        limit_error = _reward_limit_hit(data, reward, key)
        if limit_error:
            return {"success": False, "error": limit_error}
        account = _account(data, key)
        required = int(reward.get("points_required", 0))
        if required <= 0 or account["balance"] < required:
            return {"success": False, "error": "You do not have enough LP for this reward."}
        redemption_id = f"LR-{uuid.uuid4().hex[:10].upper()}"
        entry = _append_entry(
            data, key, -required, "redemption",
            f"Redeemed {reward.get('name', 'reward')}", "redemption",
            f"redemption:{redemption_id}",
            {"reward_id": reward_id, "redemption_id": redemption_id},
        )
        if not entry:
            return {"success": False, "error": "This redemption could not be completed."}
        kind = str(reward.get("kind", "manual")).lower()
        requires_review = bool(reward.get("manual_approval", kind in {"usdt", "crypto", "airtime", "data", "gift_card", "manual"}))
        redemption = {
            "id": redemption_id,
            "user_id": key,
            "reward_id": reward_id,
            "reward_name": reward.get("name", "Reward"),
            "points": required,
            "kind": kind,
            "value": reward.get("value", ""),
            "status": "pending" if requires_review else "approved",
            "created_at": _now(),
            "updated_at": _now(),
            "order_record": {
                "type": "Rewards Redemption",
                "reference": redemption_id,
                "status": "Pending Review" if requires_review else "Approved",
                "reward_value": reward.get("value", ""),
            },
        }
        data["redemptions"].append(redemption)
        return {"success": True, "redemption": redemption, "balance": int(account["balance"])}

    result = _with_lock(mutate)
    if result.get("success"):
        _mirror_legacy_points(key, result["balance"])
    return result


def review_redemption(redemption_id: str, status: str, actor: str, reason: str = "") -> dict[str, Any]:
    status = str(status).lower()
    if status not in {"approved", "rejected"}:
        return {"success": False, "error": "Invalid redemption status"}

    def mutate(data: dict[str, Any]) -> dict[str, Any]:
        redemption = next((row for row in data["redemptions"] if row.get("id") == redemption_id), None)
        if not redemption:
            return {"success": False, "error": "Redemption not found"}
        if redemption.get("status") != "pending":
            return {"success": False, "error": "This redemption has already been reviewed"}
        redemption["status"] = status
        redemption["updated_at"] = _now()
        redemption["reviewed_by"] = str(actor)
        redemption["review_reason"] = str(reason).strip()
        if status == "rejected":
            refund_key = f"refund:{redemption_id}"
            _append_entry(
                data,
                str(redemption["user_id"]),
                int(redemption["points"]),
                "redemption_refund",
                f"Refund for rejected redemption {redemption_id}",
                "redemption",
                refund_key,
                {"redemption_id": redemption_id, "actor": str(actor)},
            )
        data["audit"].append({
            "id": str(uuid.uuid4()),
            "timestamp": _now(),
            "type": "redemption_review",
            "actor": str(actor),
            "user_id": str(redemption["user_id"]),
            "reference": redemption_id,
            "status": status,
            "reason": str(reason).strip(),
        })
        balance = int(_account(data, str(redemption["user_id"]))["balance"])
        return {"success": True, "redemption": redemption, "balance": balance}

    result = _with_lock(mutate)
    if result.get("success"):
        _mirror_legacy_points(str(result["redemption"]["user_id"]), result["balance"])
    return result


def admin_save_reward(payload: dict[str, Any], reward_id: str | None, actor: str) -> dict[str, Any]:
    name = str(payload.get("name", "")).strip()
    if not name:
        return {"success": False, "error": "Reward name is required"}
    try:
        points_required = int(payload.get("points_required", 0))
    except (TypeError, ValueError):
        points_required = 0
    if points_required <= 0:
        return {"success": False, "error": "Required points must be greater than zero"}

    def mutate(data: dict[str, Any]) -> dict[str, Any]:
        reward = next((row for row in data["rewards"] if row.get("id") == reward_id), None) if reward_id else None
        if reward is None:
            reward = {"id": f"reward-{uuid.uuid4().hex[:10]}"}
            data["rewards"].append(reward)
        allowed = {
            "name", "description", "kind", "value", "points_required", "active",
            "limit", "daily_limit", "monthly_limit", "manual_approval",
        }
        for key in allowed:
            if key in payload:
                reward[key] = payload[key]
        reward["name"] = name
        reward["points_required"] = points_required
        reward["active"] = bool(payload.get("active", reward.get("active", True)))
        for key in ("limit", "daily_limit", "monthly_limit"):
            try:
                reward[key] = max(0, int(reward.get(key, 0) or 0))
            except (TypeError, ValueError):
                reward[key] = 0
        reward["updated_at"] = _now()
        reward.setdefault("created_at", _now())
        data["audit"].append({
            "id": str(uuid.uuid4()), "timestamp": _now(), "type": "reward_config",
            "actor": str(actor), "reference": reward["id"], "reason": "Reward saved",
        })
        return {"success": True, "reward": reward}

    return _with_lock(mutate)


def admin_delete_reward(reward_id: str, actor: str) -> dict[str, Any]:
    def mutate(data: dict[str, Any]) -> dict[str, Any]:
        before = len(data["rewards"])
        data["rewards"] = [row for row in data["rewards"] if row.get("id") != reward_id]
        if len(data["rewards"]) == before:
            return {"success": False, "error": "Reward not found"}
        data["audit"].append({
            "id": str(uuid.uuid4()), "timestamp": _now(), "type": "reward_deleted",
            "actor": str(actor), "reference": reward_id, "reason": "Reward deleted",
        })
        return {"success": True}
    return _with_lock(mutate)


def admin_update_action(action_key: str, payload: dict[str, Any], actor: str) -> dict[str, Any]:
    def mutate(data: dict[str, Any]) -> dict[str, Any]:
        action = data["settings"]["actions"].setdefault(action_key, {
            "label": action_key, "description": "", "points": 0, "enabled": False
        })
        for key in ("label", "description", "enabled", "once", "points", "threshold", "daily_limit"):
            if key in payload:
                action[key] = payload[key]
        for key in ("points", "threshold", "daily_limit"):
            if key in action:
                try:
                    action[key] = max(0, int(action[key] or 0))
                except (TypeError, ValueError):
                    action[key] = 0
        action["enabled"] = bool(action.get("enabled", False))
        data["audit"].append({
            "id": str(uuid.uuid4()), "timestamp": _now(), "type": "action_config",
            "actor": str(actor), "reference": action_key, "reason": "Earning action updated",
        })
        return {"success": True, "action": action}
    return _with_lock(mutate)


def admin_save_campaign(payload: dict[str, Any], campaign_id: str | None, actor: str) -> dict[str, Any]:
    name = str(payload.get("name", "")).strip()
    if not name:
        return {"success": False, "error": "Campaign name is required"}
    try:
        points = int(payload.get("points", 0))
    except (TypeError, ValueError):
        points = 0
    if points <= 0:
        return {"success": False, "error": "Campaign points must be greater than zero"}

    def mutate(data: dict[str, Any]) -> dict[str, Any]:
        campaigns = data["settings"]["campaigns"]
        campaign = next((row for row in campaigns if row.get("id") == campaign_id), None) if campaign_id else None
        if campaign is None:
            campaign = {"id": f"campaign-{uuid.uuid4().hex[:10]}"}
            campaigns.append(campaign)
        for key in ("name", "description", "starts_at", "ends_at", "enabled", "max_awards", "points"):
            if key in payload:
                campaign[key] = payload[key]
        campaign["name"] = name
        campaign["points"] = points
        campaign["enabled"] = bool(payload.get("enabled", campaign.get("enabled", True)))
        campaign["max_awards"] = max(0, int(payload.get("max_awards", campaign.get("max_awards", 0)) or 0))
        campaign.setdefault("created_at", _now())
        campaign["updated_at"] = _now()
        data["audit"].append({
            "id": str(uuid.uuid4()), "timestamp": _now(), "type": "campaign_config",
            "actor": str(actor), "reference": campaign["id"], "reason": "Campaign saved",
        })
        return {"success": True, "campaign": campaign}
    return _with_lock(mutate)


def admin_overview() -> dict[str, Any]:
    data = load_rewards_data()
    accounts = data["accounts"]
    return {
        "users": len(accounts),
        "points_outstanding": sum(int(row.get("balance", 0)) for row in accounts.values()),
        "points_issued": sum(int(row.get("lifetime_earned", 0)) for row in accounts.values()),
        "redemptions_pending": sum(1 for row in data["redemptions"] if row.get("status") == "pending"),
        "rewards": data["rewards"],
        "actions": data["settings"]["actions"],
        "campaigns": data["settings"]["campaigns"],
        "redemptions": list(reversed(data["redemptions"][-100:])),
        "ledger": list(reversed(data["ledger"][-100:])),
        "audit": list(reversed(data["audit"][-100:])),
    }


def award_verified_transaction(tx: dict[str, Any], event_id: str) -> dict[str, Any]:
    """Award only after an order moves into an approved/completed state."""
    status = str(tx.get("Status", "")).strip().lower()
    if status not in COMPLETED_STATUSES:
        return {"awarded": [], "ignored": True}
    user_id = str(tx.get("UserID", "")).strip()
    order_type = str(tx.get("Type", "")).strip().lower()
    if not user_id or order_type == "user join":
        return {"awarded": [], "ignored": True}
    event_id = str(event_id)
    amount_text = str(tx.get("Amount", "") or "")
    numbers = re.findall(r"\d[\d,]*(?:\.\d+)?", amount_text)
    volume = float(numbers[0].replace(",", "")) if numbers else 0.0
    day = str(tx.get("Timestamp", _now()))[:10]

    referred_by = None
    users = _read_json(USER_DATA_FILE, {"users": {}}).get("users", {})
    referred_by = users.get(user_id, {}).get("referred_by")

    def mutate(data: dict[str, Any]) -> dict[str, Any]:
        account = _account(data, user_id)
        if event_id in account["verified_events"]:
            return {"awarded": [], "duplicate": True, "balance": int(account["balance"])}
        previous_count = int(account["trade_count"])
        previous_volume = float(account["trade_volume"])
        account["trade_count"] = previous_count + 1
        account["trade_volume"] = round(previous_volume + volume, 8)
        if day and day not in account["trade_days"]:
            account["trade_days"].append(day)
            account["trade_days"] = account["trade_days"][-366:]
        account["verified_events"].append(event_id)
        account["last_activity"] = _now()
        awarded = []
        base = f"verified:{event_id}"
        for action_key in ("completed_trade",):
            entry = _action_entry(data, user_id, action_key, f"action:{user_id}:{action_key}:{event_id}", {"event_id": event_id, "transaction": tx})
            if entry:
                awarded.append(entry)
        if previous_count == 0:
            entry = _action_entry(data, user_id, "first_successful_trade", f"action:{user_id}:first_successful_trade:{event_id}", {"event_id": event_id})
            if entry:
                awarded.append(entry)
        for action_key in ("trading_volume_100", "trading_volume_500"):
            action = data["settings"]["actions"].get(action_key, {})
            threshold = float(action.get("threshold", 0) or 0)
            if threshold and previous_volume < threshold <= account["trade_volume"]:
                entry = _action_entry(data, user_id, action_key, f"action:{user_id}:{action_key}:{event_id}", {"event_id": event_id, "volume": account["trade_volume"]})
                if entry:
                    awarded.append(entry)
        action = data["settings"]["actions"].get("multiple_trades_5", {})
        threshold = int(action.get("threshold", 5) or 5)
        if previous_count < threshold <= account["trade_count"]:
            entry = _action_entry(data, user_id, "multiple_trades_5", f"action:{user_id}:multiple_trades_5:{event_id}", {"event_id": event_id})
            if entry:
                awarded.append(entry)
        action = data["settings"]["actions"].get("consistent_activity_7", {})
        threshold = int(action.get("threshold", 7) or 7)
        if len(account["trade_days"]) >= threshold:
            entry = _action_entry(data, user_id, "consistent_activity_7", f"action:{user_id}:consistent_activity_7:{event_id}", {"event_id": event_id})
            if entry:
                awarded.append(entry)
        if referred_by and str(referred_by) != user_id:
            ref_account = _account(data, str(referred_by))
            referral_key = f"action:{referred_by}:referral_qualifying:{user_id}"
            entry = _action_entry(data, str(referred_by), "referral_qualifying", referral_key, {"referred_user_id": user_id, "event_id": event_id})
            if entry:
                ref_account["qualified_referrals"] = int(ref_account.get("qualified_referrals", 0)) + 1
                awarded.append(entry)
        now = datetime.now()
        for campaign in data["settings"].get("campaigns", []):
            if not campaign.get("enabled", False):
                continue
            starts = str(campaign.get("starts_at", "") or "")
            ends = str(campaign.get("ends_at", "") or "")
            if starts and _now() < starts:
                continue
            if ends and _now() > ends:
                continue
            campaign_key = f"campaign:{campaign.get('id')}:{event_id}"
            if campaign.get("max_awards", 0):
                count = sum(1 for row in data["ledger"] if row.get("metadata", {}).get("campaign_id") == campaign.get("id"))
                if count >= int(campaign["max_awards"]):
                    continue
            entry = _append_entry(data, user_id, int(campaign.get("points", 0)), "campaign", str(campaign.get("name", "Campaign")), "campaign", campaign_key, {"campaign_id": campaign.get("id"), "event_id": event_id})
            if entry:
                awarded.append(entry)
        return {"awarded": awarded, "balance": int(account["balance"]), "trade_count": int(account["trade_count"])}

    result = _with_lock(mutate)
    _mirror_legacy_points(user_id, result["balance"])
    if referred_by and str(referred_by) != user_id:
        _mirror_legacy_points(str(referred_by), snapshot(str(referred_by))["points"])
    return result


def reverse_verified_transaction(tx: dict[str, Any], event_id: str, reason: str = "Transaction reversed") -> dict[str, Any]:
    user_id = str(tx.get("UserID", "")).strip()
    if not user_id:
        return {"success": False, "error": "Missing user"}
    prefix = f"verified:{event_id}"

    def mutate(data: dict[str, Any]) -> dict[str, Any]:
        source_rows = [
            row for row in data["ledger"]
            if row.get("metadata", {}).get("event_id") == event_id
            and int(row.get("delta", 0)) > 0
            and not row.get("reversal")
        ]
        reversed_rows = []
        for row in source_rows:
            reverse_key = f"reversal:{row.get('id')}"
            entry = _append_entry(data, str(row["user_id"]), -int(row["delta"]), "reversal", reason, "verified_transaction", reverse_key, {"event_id": event_id, "reverses": row.get("id")})
            if entry:
                entry["reversal"] = True
                reversed_rows.append(entry)
        account = _account(data, user_id)
        if event_id in account.get("verified_events", []):
            account["verified_events"].remove(event_id)
            account["trade_count"] = max(0, int(account["trade_count"]) - 1)
        return {"success": bool(reversed_rows), "reversed": reversed_rows, "balance": int(account["balance"])}

    result = _with_lock(mutate)
    _mirror_legacy_points(user_id, result["balance"])
    return result
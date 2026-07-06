"""
click_merchant.py — Click Merchant API (Shop API, Prepare/Complete) integratsiyasi.

payme_merchant.py bilan bir xil uslubda yozilgan (bitta DB_PATH fayl, alohida
jadvallar). bot.py ichida shunga o'xshab ulanadi:

    import click_merchant

    click_merchant.set_callbacks(
        on_paid=my_async_on_paid_function,
        on_cancel=my_async_on_cancel_function,
    )

    web_app.add_routes([
        web.post("/click/prepare", click_merchant.click_prepare_webhook),
        web.post("/click/complete", click_merchant.click_complete_webhook),
    ])

    order_id = click_merchant.create_order(chat_id, amount_sum=39000)
    url = click_merchant.build_checkout_url(order_id)

Hujjat: https://docs.click.uz/click-api-request/  (Prepare/Complete, action=0/1)
        https://docs.click.uz/en/click-api-error/ (xatolik kodlari)
"""
import os
import time
import hashlib
import logging
import sqlite3

logger = logging.getLogger("click_merchant")

# ---------------------------------------------------------------------------
# Sozlamalar (Railway'da Variables bo'limiga qo'shiladi)
# ---------------------------------------------------------------------------
CLICK_SERVICE_ID = os.environ.get("CLICK_SERVICE_ID", "").strip()
CLICK_MERCHANT_ID = os.environ.get("CLICK_MERCHANT_ID", "").strip()
CLICK_MERCHANT_USER_ID = os.environ.get("CLICK_MERCHANT_USER_ID", "").strip()
CLICK_SECRET_KEY = os.environ.get("CLICK_SECRET_KEY", "").strip()
CLICK_CHECKOUT_URL = os.environ.get("CLICK_CHECKOUT_URL", "https://my.click.uz/services/pay").strip().rstrip("/")

# Bot bilan bitta SQLite faylni bo'lishamiz
DB_PATH = os.environ.get("DB_PATH", "bot.db").strip()

ORDER_STATUS_NEW = "new"
ORDER_STATUS_WAITING = "waiting_payment"
ORDER_STATUS_PAID = "paid"
ORDER_STATUS_CANCELLED = "cancelled"

ACTION_PREPARE = 0
ACTION_COMPLETE = 1

ERROR_SUCCESS = 0
ERROR_SIGN_FAILED = -1
ERROR_WRONG_AMOUNT = -2
ERROR_ACTION_NOT_FOUND = -3
ERROR_ALREADY_PAID = -4
ERROR_USER_NOT_FOUND = -5
ERROR_TRANSACTION_NOT_FOUND = -6
ERROR_FAILED_UPDATE_USER = -7
ERROR_BAD_REQUEST = -8
ERROR_TRANSACTION_CANCELLED = -9

AMOUNT_EPS = 0.01  # Click summani float qilib yuboradi, tenglikni tolerantli tekshiramiz

REQUIRED_FIELDS = [
    "click_trans_id", "service_id", "click_paydoc_id", "merchant_trans_id",
    "amount", "action", "error", "error_note", "sign_time", "sign_string",
]

# ---------------------------------------------------------------------------
# Callbacklar (bot.py tomonidan sozlanadi)
# ---------------------------------------------------------------------------
_on_paid_callback = None     # async def(chat_id: int, order_id: int)
_on_cancel_callback = None   # async def(chat_id: int, order_id: int, reason: int)


def set_callbacks(on_paid=None, on_cancel=None):
    global _on_paid_callback, _on_cancel_callback
    _on_paid_callback = on_paid
    _on_cancel_callback = on_cancel


# ---------------------------------------------------------------------------
# SQLite
# ---------------------------------------------------------------------------

def _conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def db_init():
    """click_orders va click_transactions jadvallarini yaratish."""
    conn = _conn()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS click_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'new',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS click_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                click_trans_id TEXT UNIQUE NOT NULL,
                click_paydoc_id TEXT,
                order_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                state INTEGER NOT NULL DEFAULT 1,
                reason INTEGER,
                create_time INTEGER NOT NULL,
                perform_time INTEGER,
                cancel_time INTEGER
            );
            """
        )
        conn.commit()
        logger.info("click_merchant: jadvallar tayyor")
    finally:
        conn.close()


def now_ms() -> int:
    return int(time.time() * 1000)


# ---------------------------------------------------------------------------
# Buyurtma va checkout havolasi (bot.py chaqiradi)
# ---------------------------------------------------------------------------

def create_order(chat_id: int, amount_sum) -> int:
    """Yangi buyurtma yaratadi. amount_sum - so'mda (Click summani tiyinga emas, so'mga aylantiradi)."""
    conn = _conn()
    try:
        cur = conn.execute(
            "INSERT INTO click_orders (chat_id, amount, status) VALUES (?, ?, ?)",
            (chat_id, float(amount_sum), ORDER_STATUS_NEW),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def build_checkout_url(order_id: int, return_url: str = "") -> str:
    """Click invoys havolasi (my.click.uz/services/pay) - foydalanuvchi shu havola orqali to'laydi."""
    conn = _conn()
    try:
        row = conn.execute("SELECT amount FROM click_orders WHERE id=?", (order_id,)).fetchone()
    finally:
        conn.close()
    if row is None:
        raise ValueError(f"Buyurtma topilmadi: {order_id}")
    amount = row["amount"]

    params = [
        f"service_id={CLICK_SERVICE_ID}",
        f"merchant_id={CLICK_MERCHANT_ID}",
        f"amount={amount}",
        f"transaction_param={order_id}",
    ]
    if return_url:
        params.append(f"return_url={return_url}")

    return f"{CLICK_CHECKOUT_URL}?{'&'.join(params)}"


# ---------------------------------------------------------------------------
# Xatolar
# ---------------------------------------------------------------------------

class ClickException(Exception):
    def __init__(self, error_code: int, error_note: str):
        self.error_code = error_code
        self.error_note = error_note
        super().__init__(error_note)


def _base_response(request: dict, error_code: int, error_note: str, extra: dict = None) -> dict:
    resp = {
        "click_trans_id": request.get("click_trans_id"),
        "merchant_trans_id": request.get("merchant_trans_id"),
        "error": error_code,
        "error_note": error_note,
    }
    if extra:
        resp.update(extra)
    return resp


# ---------------------------------------------------------------------------
# Imzo tekshirish
# ---------------------------------------------------------------------------

def _verify_sign(request: dict, action: int) -> bool:
    if action == ACTION_PREPARE:
        raw = (
            f"{request.get('click_trans_id')}{request.get('service_id')}{CLICK_SECRET_KEY}"
            f"{request.get('merchant_trans_id')}{request.get('amount')}{action}{request.get('sign_time')}"
        )
    else:
        raw = (
            f"{request.get('click_trans_id')}{request.get('service_id')}{CLICK_SECRET_KEY}"
            f"{request.get('merchant_trans_id')}{request.get('merchant_prepare_id')}"
            f"{request.get('amount')}{action}{request.get('sign_time')}"
        )
    expected = hashlib.md5(raw.encode("utf-8")).hexdigest()
    return expected == str(request.get("sign_string"))


# ---------------------------------------------------------------------------
# Yordamchi: order/transaction CRUD
# ---------------------------------------------------------------------------

def _get_order(conn, order_id: int):
    return conn.execute("SELECT * FROM click_orders WHERE id=?", (order_id,)).fetchone()


def _get_txn_by_click_id(conn, click_trans_id: str):
    return conn.execute(
        "SELECT * FROM click_transactions WHERE click_trans_id=?", (click_trans_id,)
    ).fetchone()


# ---------------------------------------------------------------------------
# Merchant API metodlari (Prepare / Complete)
# ---------------------------------------------------------------------------

def handle_prepare(request: dict) -> dict:
    for f in REQUIRED_FIELDS:
        if f not in request:
            raise ClickException(ERROR_BAD_REQUEST, "Error in request from click")

    if not _verify_sign(request, ACTION_PREPARE):
        raise ClickException(ERROR_SIGN_FAILED, "SIGN CHECK FAILED!")

    try:
        action = int(request["action"])
    except (TypeError, ValueError):
        raise ClickException(ERROR_ACTION_NOT_FOUND, "Action not found")
    if action != ACTION_PREPARE:
        raise ClickException(ERROR_ACTION_NOT_FOUND, "Action not found")

    try:
        order_id = int(request["merchant_trans_id"])
    except (TypeError, ValueError):
        raise ClickException(ERROR_USER_NOT_FOUND, "User does not exist")

    click_trans_id = str(request["click_trans_id"])

    conn = _conn()
    try:
        order = _get_order(conn, order_id)
        if order is None:
            raise ClickException(ERROR_USER_NOT_FOUND, "User does not exist")

        if order["status"] == ORDER_STATUS_CANCELLED:
            raise ClickException(ERROR_TRANSACTION_CANCELLED, "Transaction cancelled")
        if order["status"] == ORDER_STATUS_PAID:
            raise ClickException(ERROR_ALREADY_PAID, "Already paid")

        try:
            amount = float(request["amount"])
        except (TypeError, ValueError):
            raise ClickException(ERROR_WRONG_AMOUNT, "Incorrect parameter amount")
        if abs(amount - float(order["amount"])) > AMOUNT_EPS:
            raise ClickException(ERROR_WRONG_AMOUNT, "Incorrect parameter amount")

        existing = _get_txn_by_click_id(conn, click_trans_id)
        if existing is not None:
            return _base_response(request, ERROR_SUCCESS, "Success", {
                "merchant_prepare_id": existing["id"],
            })

        create_time = now_ms()
        cur = conn.execute(
            "INSERT INTO click_transactions "
            "(click_trans_id, click_paydoc_id, order_id, amount, state, create_time) "
            "VALUES (?, ?, ?, ?, 1, ?)",
            (click_trans_id, str(request.get("click_paydoc_id", "")), order_id, amount, create_time),
        )
        conn.execute(
            "UPDATE click_orders SET status=? WHERE id=?",
            (ORDER_STATUS_WAITING, order_id),
        )
        conn.commit()
        prepare_id = cur.lastrowid

        return _base_response(request, ERROR_SUCCESS, "Success", {
            "merchant_prepare_id": prepare_id,
        })
    finally:
        conn.close()


def handle_complete(request: dict):
    """
    Natija: (rpc_result_dict, event)
    event - None, yoki ("paid", chat_id, order_id), yoki ("cancelled", chat_id, order_id, reason)
    """
    for f in REQUIRED_FIELDS:
        if f not in request:
            raise ClickException(ERROR_BAD_REQUEST, "Error in request from click")
    if "merchant_prepare_id" not in request:
        raise ClickException(ERROR_BAD_REQUEST, "Error in request from click")

    if not _verify_sign(request, ACTION_COMPLETE):
        raise ClickException(ERROR_SIGN_FAILED, "SIGN CHECK FAILED!")

    try:
        action = int(request["action"])
    except (TypeError, ValueError):
        raise ClickException(ERROR_ACTION_NOT_FOUND, "Action not found")
    if action != ACTION_COMPLETE:
        raise ClickException(ERROR_ACTION_NOT_FOUND, "Action not found")

    try:
        order_id = int(request["merchant_trans_id"])
    except (TypeError, ValueError):
        raise ClickException(ERROR_USER_NOT_FOUND, "User does not exist")

    try:
        prepare_id = int(request["merchant_prepare_id"])
    except (TypeError, ValueError):
        raise ClickException(ERROR_TRANSACTION_NOT_FOUND, "Transaction does not exist")

    conn = _conn()
    try:
        order = _get_order(conn, order_id)
        if order is None:
            raise ClickException(ERROR_USER_NOT_FOUND, "User does not exist")

        txn = conn.execute(
            "SELECT * FROM click_transactions WHERE id=?", (prepare_id,)
        ).fetchone()
        if txn is None:
            raise ClickException(ERROR_TRANSACTION_NOT_FOUND, "Transaction does not exist")

        try:
            click_error = int(request["error"])
        except (TypeError, ValueError):
            click_error = -1

        # Click tomonidan bekor qilingan / muvaffaqiyatsiz tolov (error < 0)
        if click_error < 0:
            if txn["state"] == 2:
                raise ClickException(ERROR_ALREADY_PAID, "Already paid")
            if txn["state"] in (-1, -2):
                return _base_response(request, ERROR_SUCCESS, "Success", {
                    "merchant_confirm_id": txn["id"],
                }), None

            cancel_time = now_ms()
            conn.execute(
                "UPDATE click_transactions SET state=-1, reason=?, cancel_time=? WHERE id=?",
                (click_error, cancel_time, prepare_id),
            )
            conn.execute(
                "UPDATE click_orders SET status=? WHERE id=?",
                (ORDER_STATUS_CANCELLED, order_id),
            )
            conn.commit()
            return _base_response(request, ERROR_SUCCESS, "Success", {
                "merchant_confirm_id": txn["id"],
            }), ("cancelled", order["chat_id"], order_id, click_error)

        # Muvaffaqiyatli to'lov
        if txn["state"] == 2:
            return _base_response(request, ERROR_ALREADY_PAID, "Already paid"), None
        if txn["state"] in (-1, -2):
            raise ClickException(ERROR_TRANSACTION_CANCELLED, "Transaction cancelled")

        try:
            amount = float(request["amount"])
        except (TypeError, ValueError):
            raise ClickException(ERROR_WRONG_AMOUNT, "Incorrect parameter amount")
        if abs(amount - float(txn["amount"])) > AMOUNT_EPS:
            raise ClickException(ERROR_WRONG_AMOUNT, "Incorrect parameter amount")

        perform_time = now_ms()
        conn.execute(
            "UPDATE click_transactions SET state=2, perform_time=? WHERE id=?",
            (perform_time, prepare_id),
        )
        conn.execute(
            "UPDATE click_orders SET status=? WHERE id=?",
            (ORDER_STATUS_PAID, order_id),
        )
        conn.commit()

        return _base_response(request, ERROR_SUCCESS, "Success", {
            "merchant_confirm_id": txn["id"],
        }), ("paid", order["chat_id"], order_id)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# aiohttp webhook handlerlar
# ---------------------------------------------------------------------------

async def _parse_request(request) -> dict:
    """Click so'rovi odatda application/x-www-form-urlencoded shaklida keladi."""
    try:
        data = await request.post()
        if data:
            return dict(data)
    except Exception:
        pass
    try:
        return dict(await request.json())
    except Exception:
        return {}


async def click_prepare_webhook(request):
    """aiohttp route handler: POST /click/prepare"""
    from aiohttp import web

    payload = await _parse_request(request)
    try:
        result = handle_prepare(payload)
        return web.json_response(result, status=200)
    except ClickException as exc:
        return web.json_response(_base_response(payload, exc.error_code, exc.error_note), status=200)
    except Exception:
        logger.exception("Click prepare webhookda kutilmagan xatolik")
        return web.json_response(
            _base_response(payload, ERROR_BAD_REQUEST, "Error in request from click"), status=200
        )


async def click_complete_webhook(request):
    """aiohttp route handler: POST /click/complete"""
    from aiohttp import web

    payload = await _parse_request(request)
    try:
        result, event = handle_complete(payload)
        if event:
            kind = event[0]
            if kind == "paid" and _on_paid_callback:
                _, chat_id, order_id = event
                await _on_paid_callback(chat_id, order_id)
            elif kind == "cancelled" and _on_cancel_callback:
                _, chat_id, order_id, reason = event
                await _on_cancel_callback(chat_id, order_id, reason)
        return web.json_response(result, status=200)
    except ClickException as exc:
        return web.json_response(_base_response(payload, exc.error_code, exc.error_note), status=200)
    except Exception:
        logger.exception("Click complete webhookda kutilmagan xatolik")
        return web.json_response(
            _base_response(payload, ERROR_BAD_REQUEST, "Error in request from click"), status=200
        )

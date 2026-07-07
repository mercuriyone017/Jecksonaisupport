"""
payme_merchant.py — Payme Merchant API (JSON-RPC 2.0) integratsiyasi.

Jeckson AI Support botiga qo'shimcha modul sifatida ulanadi. Mavjud bot.py'dagi
sqlite3 uslubiga mos yozilgan (bir xil DB_PATH fayldan foydalanadi, alohida jadvallar).

Hujjat: https://developer.help.paycom.uz/metody-merchant-api/

Ishlatilishi (bot.py ichida):

    import payme_merchant

    payme_merchant.set_callbacks(
        on_paid=my_async_on_paid_function,
        on_cancel=my_async_on_cancel_function,
    )

    # aiohttp route sifatida ulash:
    web_app.add_routes([web.post("/pay", payme_merchant.payme_webhook)])

    # to'lov buyurtmasi yaratish va checkout havolasini olish:
    order_id = payme_merchant.create_order(chat_id, amount_sum=39000)
    url = payme_merchant.build_checkout_url(order_id)
"""
import os
import json
import time
import base64
import binascii
import hmac
import logging
import sqlite3

logger = logging.getLogger("payme_merchant")

# ---------------------------------------------------------------------------
# Sozlamalar (Railway'da Variables bo'limiga qo'shiladi)
# ---------------------------------------------------------------------------
PAYME_MERCHANT_ID = os.environ.get("PAYME_MERCHANT_ID", "").strip()
PAYME_KEY = os.environ.get("PAYME_KEY", "").strip()
PAYME_CHECKOUT_URL = os.environ.get("PAYME_CHECKOUT_URL", "https://checkout.test.paycom.uz").strip().rstrip("/")
PAYME_ACCOUNT_FIELD = os.environ.get("PAYME_ACCOUNT_FIELD", "order_id").strip()

# Fiskalizatsiya uchun mahsulot ma'lumotlari
PAYME_PRODUCT_TITLE = os.environ.get("PAYME_PRODUCT_TITLE", "AI Darslik").strip()
PAYME_PRODUCT_CODE = os.environ.get("PAYME_PRODUCT_CODE", "").strip()          # MXIK/IKPU kodi
PAYME_PRODUCT_PACKAGE_CODE = os.environ.get("PAYME_PRODUCT_PACKAGE_CODE", "").strip()
PAYME_PRODUCT_VAT_PERCENT = int(os.environ.get("PAYME_PRODUCT_VAT_PERCENT", "15"))

# Bot bilan bitta SQLite faylni bo'lishamiz
DB_PATH = os.environ.get("DB_PATH", "bot.db").strip()

TRANSACTION_TIMEOUT_MS = int(os.environ.get("PAYME_TRANSACTION_TIMEOUT_MS", "43200000"))  # 12 soat (Payme protokoli talabi, test uchun Railway Variables orqali qisqartirish mumkin)

ORDER_STATUS_NEW = "new"
ORDER_STATUS_WAITING = "waiting_payment"
ORDER_STATUS_PAID = "paid"
ORDER_STATUS_CANCELLED = "cancelled"


# ---------------------------------------------------------------------------
# Callbacklar (bot.py tomonidan sozlanadi - PTB Application/Bot obyektiga kirish uchun)
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
    """payme_orders va payme_transactions jadvallarini yaratish."""
    conn = _conn()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS payme_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                amount INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'new',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS payme_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                payme_id TEXT UNIQUE NOT NULL,
                order_id INTEGER NOT NULL,
                amount INTEGER NOT NULL,
                account_value TEXT,
                state INTEGER NOT NULL DEFAULT 1,
                reason INTEGER,
                payme_time INTEGER,
                create_time INTEGER NOT NULL,
                perform_time INTEGER,
                cancel_time INTEGER,
                fiscal_perform_data TEXT,
                fiscal_cancel_data TEXT
            );
            """
        )
        conn.commit()
        logger.info("payme_merchant: jadvallar tayyor")
    finally:
        conn.close()


def now_ms() -> int:
    return int(time.time() * 1000)


# ---------------------------------------------------------------------------
# Buyurtma va checkout havolasi (bot.py chaqiradi)
# ---------------------------------------------------------------------------

def create_order(chat_id: int, amount_sum: int) -> int:
    """Yangi buyurtma yaratadi. amount_sum - so'mda, ichkarida tiyinga o'tkaziladi."""
    amount_tiyin = int(round(amount_sum * 100))
    conn = _conn()
    try:
        cur = conn.execute(
            "INSERT INTO payme_orders (chat_id, amount, status) VALUES (?, ?, ?)",
            (chat_id, amount_tiyin, ORDER_STATUS_NEW),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def build_checkout_url(order_id: int, return_url: str = "") -> str:
    """Payme checkout sahifasiga olib boruvchi havola (GET usuli, base64)."""
    conn = _conn()
    try:
        row = conn.execute("SELECT amount FROM payme_orders WHERE id=?", (order_id,)).fetchone()
    finally:
        conn.close()
    if row is None:
        raise ValueError(f"Buyurtma topilmadi: {order_id}")
    amount = row["amount"]

    parts = [
        f"m={PAYME_MERCHANT_ID}",
        f"ac.{PAYME_ACCOUNT_FIELD}={order_id}",
        f"a={amount}",
        "l=uz",
    ]
    if return_url:
        parts.append(f"c={return_url}")

    raw = ";".join(parts)
    encoded = base64.b64encode(raw.encode("utf-8")).decode("utf-8")
    return f"{PAYME_CHECKOUT_URL}/{encoded}"


# ---------------------------------------------------------------------------
# Auth (Basic base64(Paycom:KEY))
# ---------------------------------------------------------------------------

def is_authorized(authorization_header) -> bool:
    if not authorization_header:
        return False
    parts = authorization_header.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "basic":
        return False
    try:
        decoded = base64.b64decode(parts[1]).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        return False
    if ":" not in decoded:
        return False
    _login, _, password = decoded.partition(":")
    return hmac.compare_digest(password, PAYME_KEY)


# ---------------------------------------------------------------------------
# Xatolar
# ---------------------------------------------------------------------------

class PaymeException(Exception):
    def __init__(self, code: int, message, data=None):
        if isinstance(message, str):
            message = {"ru": message, "uz": message, "en": message}
        self.code = code
        self.message = message
        self.data = data
        super().__init__(str(message))

    def as_rpc_error(self):
        err = {"code": self.code, "message": self.message}
        if self.data is not None:
            err["data"] = self.data
        return err


ERR_METHOD_NOT_POST = -32300
ERR_PARSE_ERROR = -32700
ERR_INVALID_RPC_OBJECT = -32600
ERR_METHOD_NOT_FOUND = -32601
ERR_INSUFFICIENT_PRIVILEGE = -32504
ERR_INTERNAL_SYSTEM = -32400

ERR_INVALID_AMOUNT = -31001
ERR_TRANSACTION_NOT_FOUND = -31003
ERR_COULD_NOT_CANCEL = -31007
ERR_COULD_NOT_PERFORM = -31008
ERR_ACCOUNT_NOT_FOUND = -31050
ERR_ACCOUNT_ALREADY_PROCESSED = -31051


def _account_error(field_name: str, message: str) -> PaymeException:
    return PaymeException(ERR_ACCOUNT_NOT_FOUND, message, data=field_name)


# ---------------------------------------------------------------------------
# Yordamchi: order/transaction CRUD
# ---------------------------------------------------------------------------

def _get_order(conn, order_id: int):
    return conn.execute("SELECT * FROM payme_orders WHERE id=?", (order_id,)).fetchone()


def _get_txn(conn, payme_id: str):
    return conn.execute("SELECT * FROM payme_transactions WHERE payme_id=?", (payme_id,)).fetchone()


def _find_order_by_account(conn, account: dict):
    raw_value = account.get(PAYME_ACCOUNT_FIELD)
    if raw_value is None:
        raise _account_error(PAYME_ACCOUNT_FIELD, "Buyurtma raqami topilmadi")
    try:
        order_id = int(raw_value)
    except (TypeError, ValueError):
        raise _account_error(PAYME_ACCOUNT_FIELD, "Buyurtma raqami noto'g'ri")
    order = _get_order(conn, order_id)
    if order is None:
        raise _account_error(PAYME_ACCOUNT_FIELD, "Bunday buyurtma topilmadi")
    return order


def _fiscal_detail() -> dict:
    item = {
        "title": PAYME_PRODUCT_TITLE,
        "price": None,  # pastda to'ldiriladi (order summasiga qarab)
        "count": 1,
        "code": PAYME_PRODUCT_CODE,
        "package_code": PAYME_PRODUCT_PACKAGE_CODE,
        "vat_percent": PAYME_PRODUCT_VAT_PERCENT,
    }
    return item


# ---------------------------------------------------------------------------
# Merchant API metodlari
# ---------------------------------------------------------------------------

def check_perform_transaction(params: dict) -> dict:
    amount = params.get("amount")
    account = params.get("account", {})

    conn = _conn()
    try:
        order = _find_order_by_account(conn, account)

        if order["status"] == ORDER_STATUS_PAID:
            raise PaymeException(ERR_ACCOUNT_ALREADY_PROCESSED, "Buyurtma allaqachon to'langan", data=PAYME_ACCOUNT_FIELD)
        if order["status"] == ORDER_STATUS_CANCELLED:
            raise PaymeException(ERR_ACCOUNT_ALREADY_PROCESSED, "Buyurtma bekor qilingan", data=PAYME_ACCOUNT_FIELD)
        if amount != order["amount"]:
            raise PaymeException(ERR_INVALID_AMOUNT, "Noto'g'ri summa")

        item = _fiscal_detail()
        item["price"] = order["amount"]

        return {
            "allow": True,
            "detail": {
                "receipt_type": 0,
                "items": [item],
            },
        }
    finally:
        conn.close()


def create_transaction(params: dict) -> dict:
    payme_id = params.get("id")
    payme_time = params.get("time")
    amount = params.get("amount")
    account = params.get("account", {})

    conn = _conn()
    try:
        existing = _get_txn(conn, payme_id)

        if existing is not None:
            if existing["state"] == 1 and (now_ms() - existing["create_time"]) > TRANSACTION_TIMEOUT_MS:
                conn.execute(
                    "UPDATE payme_transactions SET state=-1, reason=4, cancel_time=? WHERE payme_id=?",
                    (now_ms(), payme_id),
                )
                conn.execute(
                    "UPDATE payme_orders SET status=? WHERE id=?",
                    (ORDER_STATUS_CANCELLED, existing["order_id"]),
                )
                conn.commit()
                raise PaymeException(ERR_COULD_NOT_PERFORM, "Tranzaksiya vaqti tugagan")

            return {
                "create_time": existing["create_time"],
                "transaction": str(existing["order_id"]),
                "state": existing["state"],
            }

        order = _find_order_by_account(conn, account)

        active = conn.execute(
            "SELECT * FROM payme_transactions WHERE order_id=? AND state IN (1,2)",
            (order["id"],),
        ).fetchone()
        if active is not None:
            if active["state"] == 1 and (now_ms() - active["create_time"]) > TRANSACTION_TIMEOUT_MS:
                # Eskirgan (12 soatdan oshgan) tugallanmagan tranzaksiya - avtomatik bekor qilib, yangisiga yol beramiz
                conn.execute(
                    "UPDATE payme_transactions SET state=-1, reason=4, cancel_time=? WHERE payme_id=?",
                    (now_ms(), active["payme_id"]),
                )
                conn.commit()
            elif active["state"] == 1:
                raise _account_error(PAYME_ACCOUNT_FIELD, "Ushbu buyurtma uchun tranzaksiya allaqachon mavjud")
            # active["state"] == 2 (tolangan) holatini pastdagi ORDER_STATUS_PAID tekshiruvi hal qiladi

        if order["status"] == ORDER_STATUS_PAID:
            raise _account_error(PAYME_ACCOUNT_FIELD, "Buyurtma allaqachon to'langan")

        if amount != order["amount"]:
            raise PaymeException(ERR_INVALID_AMOUNT, "Noto'g'ri summa")

        account_value = str(account.get(PAYME_ACCOUNT_FIELD, ""))
        create_time = now_ms()

        conn.execute(
            "INSERT INTO payme_transactions "
            "(payme_id, order_id, amount, account_value, state, payme_time, create_time) "
            "VALUES (?, ?, ?, ?, 1, ?, ?)",
            (payme_id, order["id"], amount, account_value, payme_time, create_time),
        )
        conn.execute(
            "UPDATE payme_orders SET status=? WHERE id=?",
            (ORDER_STATUS_WAITING, order["id"]),
        )
        conn.commit()

        return {
            "create_time": create_time,
            "transaction": str(order["id"]),
            "state": 1,
        }
    finally:
        conn.close()


def perform_transaction(params: dict) -> tuple[dict, tuple | None]:
    """
    Natija: (rpc_result, paid_event)
    paid_event - None yoki (chat_id, order_id) - agar shu chaqiruvda to'lov
    birinchi marta muvaffaqiyatli yakunlangan bo'lsa (webhookda callback chaqirish uchun).
    """
    payme_id = params.get("id")

    conn = _conn()
    try:
        txn = _get_txn(conn, payme_id)
        if txn is None:
            raise PaymeException(ERR_TRANSACTION_NOT_FOUND, "Tranzaksiya topilmadi")

        if txn["state"] == 2:
            return {
                "transaction": str(txn["order_id"]),
                "perform_time": txn["perform_time"],
                "state": 2,
            }, None

        if txn["state"] != 1:
            raise PaymeException(ERR_COULD_NOT_PERFORM, "Bu amalni bajarib bo'lmaydi")

        if (now_ms() - txn["create_time"]) > TRANSACTION_TIMEOUT_MS:
            conn.execute(
                "UPDATE payme_transactions SET state=-1, reason=4, cancel_time=? WHERE payme_id=?",
                (now_ms(), payme_id),
            )
            conn.execute(
                "UPDATE payme_orders SET status=? WHERE id=?",
                (ORDER_STATUS_CANCELLED, txn["order_id"]),
            )
            conn.commit()
            raise PaymeException(ERR_COULD_NOT_PERFORM, "Tranzaksiya vaqti tugagan")

        perform_time = now_ms()
        conn.execute(
            "UPDATE payme_transactions SET state=2, perform_time=? WHERE payme_id=?",
            (perform_time, payme_id),
        )

        order = _get_order(conn, txn["order_id"])
        conn.execute(
            "UPDATE payme_orders SET status=? WHERE id=?",
            (ORDER_STATUS_PAID, txn["order_id"]),
        )
        conn.commit()

        return {
            "transaction": str(txn["order_id"]),
            "perform_time": perform_time,
            "state": 2,
        }, (order["chat_id"], txn["order_id"])
    finally:
        conn.close()


def cancel_transaction(params: dict):
    payme_id = params.get("id")
    reason = params.get("reason")

    conn = _conn()
    try:
        txn = _get_txn(conn, payme_id)
        if txn is None:
            raise PaymeException(ERR_TRANSACTION_NOT_FOUND, "Tranzaksiya topilmadi")

        if txn["state"] in (-1, -2):
            return {
                "transaction": str(txn["order_id"]),
                "cancel_time": txn["cancel_time"],
                "state": txn["state"],
            }, None

        new_state = -1 if txn["state"] == 1 else -2
        cancel_time = now_ms()
        conn.execute(
            "UPDATE payme_transactions SET state=?, reason=?, cancel_time=? WHERE payme_id=?",
            (new_state, reason, cancel_time, payme_id),
        )
        order = _get_order(conn, txn["order_id"])
        conn.execute(
            "UPDATE payme_orders SET status=? WHERE id=?",
            (ORDER_STATUS_CANCELLED, txn["order_id"]),
        )
        conn.commit()

        return {
            "transaction": str(txn["order_id"]),
            "cancel_time": cancel_time,
            "state": new_state,
        }, (order["chat_id"], txn["order_id"], reason)
    finally:
        conn.close()


def check_transaction(params: dict) -> dict:
    payme_id = params.get("id")
    conn = _conn()
    try:
        txn = _get_txn(conn, payme_id)
        if txn is None:
            raise PaymeException(ERR_TRANSACTION_NOT_FOUND, "Tranzaksiya topilmadi")
        return {
            "create_time": txn["create_time"],
            "perform_time": txn["perform_time"] or 0,
            "cancel_time": txn["cancel_time"] or 0,
            "transaction": str(txn["order_id"]),
            "state": txn["state"],
            "reason": txn["reason"],
        }
    finally:
        conn.close()


def get_statement(params: dict) -> dict:
    from_ts = params.get("from")
    to_ts = params.get("to")
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT * FROM payme_transactions WHERE create_time >= ? AND create_time <= ? "
            "ORDER BY create_time ASC",
            (from_ts, to_ts),
        ).fetchall()
        transactions = []
        for txn in rows:
            transactions.append({
                "id": txn["payme_id"],
                "time": txn["payme_time"],
                "amount": txn["amount"],
                "account": {PAYME_ACCOUNT_FIELD: txn["account_value"]},
                "create_time": txn["create_time"],
                "perform_time": txn["perform_time"] or 0,
                "cancel_time": txn["cancel_time"] or 0,
                "transaction": str(txn["order_id"]),
                "state": txn["state"],
                "reason": txn["reason"],
            })
        return {"transactions": transactions}
    finally:
        conn.close()


def set_fiscal_data(params: dict) -> dict:
    payme_id = params.get("id")
    fiscal_type = params.get("type")
    fiscal_data = params.get("fiscal_data")

    conn = _conn()
    try:
        txn = _get_txn(conn, payme_id)
        if txn is None:
            raise PaymeException(-32001, "Chek topilmadi")
        payload = json.dumps(fiscal_data, ensure_ascii=False)
        column = "fiscal_cancel_data" if fiscal_type == "CANCEL" else "fiscal_perform_data"
        conn.execute(f"UPDATE payme_transactions SET {column}=? WHERE payme_id=?", (payload, payme_id))
        conn.commit()
        return {"success": True}
    finally:
        conn.close()


METHODS = {
    "CheckPerformTransaction": check_perform_transaction,
    "CreateTransaction": create_transaction,
    "CheckTransaction": check_transaction,
    "GetStatement": get_statement,
    "SetFiscalData": set_fiscal_data,
}
# perform_transaction va cancel_transaction alohida ishlaydi (tuple qaytaradi, callback chaqiradi)


# ---------------------------------------------------------------------------
# aiohttp webhook handler
# ---------------------------------------------------------------------------

async def payme_webhook(request):
    """
    aiohttp route handler: POST /pay
    bot.py da: web_app.add_routes([web.post("/pay", payme_merchant.payme_webhook)])
    """
    from aiohttp import web  # lokal import - aiohttp faqat shu yerda kerak

    request_id = None
    try:
        if not is_authorized(request.headers.get("Authorization")):
            return web.json_response(
                {"jsonrpc": "2.0", "id": None, "error": PaymeException(ERR_INSUFFICIENT_PRIVILEGE, "Ruxsat yo'q").as_rpc_error()},
                status=200,
            )

        try:
            payload = await request.json()
        except json.JSONDecodeError:
            return web.json_response(
                {"jsonrpc": "2.0", "id": None, "error": PaymeException(ERR_PARSE_ERROR, "JSON xato").as_rpc_error()},
                status=200,
            )

        request_id = payload.get("id")
        method = payload.get("method")
        params = payload.get("params")

        if not isinstance(method, str) or not isinstance(params, dict):
            return web.json_response(
                {"jsonrpc": "2.0", "id": request_id, "error": PaymeException(ERR_INVALID_RPC_OBJECT, "So'rov formati noto'g'ri").as_rpc_error()},
                status=200,
            )

        if method == "PerformTransaction":
            result, paid_event = perform_transaction(params)
            if paid_event and _on_paid_callback:
                chat_id, order_id = paid_event
                await _on_paid_callback(chat_id, order_id)
            return web.json_response({"jsonrpc": "2.0", "id": request_id, "result": result}, status=200)

        if method == "CancelTransaction":
            result, cancel_event = cancel_transaction(params)
            if cancel_event and _on_cancel_callback:
                chat_id, order_id, reason = cancel_event
                await _on_cancel_callback(chat_id, order_id, reason)
            return web.json_response({"jsonrpc": "2.0", "id": request_id, "result": result}, status=200)

        handler_fn = METHODS.get(method)
        if handler_fn is None:
            return web.json_response(
                {"jsonrpc": "2.0", "id": request_id, "error": PaymeException(ERR_METHOD_NOT_FOUND, "Metod topilmadi", data=method).as_rpc_error()},
                status=200,
            )

        result = handler_fn(params)
        return web.json_response({"jsonrpc": "2.0", "id": request_id, "result": result}, status=200)

    except PaymeException as exc:
        return web.json_response({"jsonrpc": "2.0", "id": request_id, "error": exc.as_rpc_error()}, status=200)
    except Exception:
        logger.exception("Payme webhookda kutilmagan xatolik")
        return web.json_response(
            {"jsonrpc": "2.0", "id": request_id, "error": PaymeException(ERR_INTERNAL_SYSTEM, "Ichki tizim xatosi").as_rpc_error()},
            status=200,
        )

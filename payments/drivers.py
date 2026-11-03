"""
Драйверы оплаты — абстракция поверх провайдеров (терминалы/эквайринг).

Бизнес-логика дёргает driver.charge(payment) и не знает деталей конкретного
устройства. Реальные драйверы (Эвотор/АТОЛ/онлайн-эквайринг) регистрируются
здесь же. 54-ФЗ: фискализация — ответственность драйвера (вернуть/проставить
fiscal_receipt_id при реальной интеграции).

Команда на физический смарт-терминал (Эвотор/АТОЛ) идёт через их API/SDK, ответ
асинхронный (вебхук/поллинг) → статус SENT, затем PAID по подтверждению.
"""
import secrets
from dataclasses import dataclass


@dataclass
class ChargeResult:
    ok: bool
    status: str            # "sent" | "paid" | "failed"
    external_id: str = ""
    message: str = ""


class PaymentDriver:
    code = ""
    label = ""

    def charge(self, payment) -> ChargeResult:
        raise NotImplementedError


_DRIVERS: dict[str, PaymentDriver] = {}


def register(driver: PaymentDriver) -> PaymentDriver:
    _DRIVERS[driver.code] = driver
    return driver


def get_driver(code: str) -> PaymentDriver | None:
    return _DRIVERS.get(code)


def all_drivers() -> list[PaymentDriver]:
    return list(_DRIVERS.values())


# --- Эмуляция терминала (для разработки/демо, пока нет живого устройства) ---
class TerminalStubDriver(PaymentDriver):
    code = "terminal_stub"
    label = "Терминал (эмуляция)"

    def charge(self, payment) -> ChargeResult:
        # В проде здесь: команда на смарт-терминал + ожидание подтверждения + чек ОФД.
        # Тут: помечаем «отправлено на терминал», подтверждение приходит отдельно
        # (кнопкой/вебхуком) → статус станет PAID.
        return ChargeResult(
            ok=True, status="sent",
            external_id="SIM-" + secrets.token_hex(4).upper(),
            message="Сумма отправлена на терминал, ожидается оплата клиентом",
        )


register(TerminalStubDriver())


# --- Реальные драйверы: заглушки под будущую интеграцию ---
class _TodoDriver(PaymentDriver):
    def charge(self, payment) -> ChargeResult:
        raise NotImplementedError(f"Драйвер «{self.label}» ещё не подключён")


class EvotorDriver(_TodoDriver):
    code = "evotor"
    label = "Эвотор (смарт-терминал)"


class AtolDriver(_TodoDriver):
    code = "atol"
    label = "АТОЛ (смарт-терминал)"


register(EvotorDriver())
register(AtolDriver())


# Драйвер по умолчанию (позже — выбор на уровне тенанта: Tenant.payment_provider)
DEFAULT_DRIVER = "terminal_stub"

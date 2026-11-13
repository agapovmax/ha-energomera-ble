"""Константы интеграции Энергомера BLE."""

DOMAIN = "energomera_ble"

CONF_PIN = "pin"
CONF_SERIAL = "serial"

DEFAULT_SCAN_INTERVAL = 120  # секунд
MIN_SCAN_INTERVAL = 30
MAX_SCAN_INTERVAL = 3600

# Сколько держать последние данные, если счётчик временно не ответил
# (слабый сигнал), прежде чем объекты станут "недоступны".
STALE_DATA_TOLERANCE = 900  # секунд

NAME_PREFIXES = ("CE308", "CE208")
MANUFACTURER = "Энергомера"

SERVICE_UUID = "b91b0100-8bef-45e2-97c3-1cd862d914df"
TX_UUID = "b91b0105-8bef-45e2-97c3-1cd862d914df"
RX_UUIDS = [f"b91b01{n:02x}-8bef-45e2-97c3-1cd862d914df" for n in range(0x06, 0x15)]

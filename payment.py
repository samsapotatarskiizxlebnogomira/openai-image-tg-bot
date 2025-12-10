# payment.py
from aiocryptopay import AioCryptoPay, Networks
import config

# Поддерживаем оба варианта именования из .env: MAINNET / TESTNET ИЛИ MAIN_NET / TEST_NET
network_raw = (getattr(config, "CRYPTOPAY_NETWORK", None) or "MAINNET").strip().upper()

# Нормализуем строку в enum
if "TEST" in network_raw:
    network = Networks.TEST_NET
else:
    network = Networks.MAIN_NET

# Токен: поддерживаем обе переменные окружения
token = (
    getattr(config, "CRYPTOPAY_TOKEN", None)
    or getattr(config, "CRYPTOBOT_TOKEN", None)  # твой текущий .env
)

if not token:
    raise RuntimeError("CryptoPay token is missing. Set CRYPTOPAY_TOKEN or CRYPTOBOT_TOKEN in .env")

cryptopay = AioCryptoPay(token=token, network=network)

async def create_invoice(amount_ton: float, user_id: int, generations: int) -> str:
    """
    Создаёт счёт в TON. В description шьём '<user_id>:<gens>' для начисления.
    """
    description = f"{user_id}:{generations}"
    inv = await cryptopay.create_invoice(
        asset="TON",
        amount=str(amount_ton),
        description=description,
    )
    return inv.pay_url
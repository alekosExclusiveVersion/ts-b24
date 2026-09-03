from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from b24_client import B24Client

c = B24Client()
prof = c.call("profile")
print(f"Пользователь: {prof['result']['NAME']} {prof['result']['LAST_NAME']} (ID {prof['result']['ID']})")

deals = c.call("crm.deal.list", {"limit": 2, "select": ["ID", "TITLE", "OPPORTUNITY"]})
print(f"Сделок проверка: получено {len(deals.get('result', []))}, всего {deals.get('total')}")

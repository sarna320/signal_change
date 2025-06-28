import csv
import asyncio
from bittensor.core.async_subtensor import get_async_subtensor, AsyncSubtensor
from tqdm import tqdm
from typing import List, Dict

# TUTAJ podaj ten sam STEP, którego użyłeś w pierwotnym skrypcie
STEP = 100

# Pola top-level vs. identity
TOP_LEVEL = {"owner_hotkey", "owner_coldkey", "subnet_name"}
IDENTITY = {"github_repo", "subnet_contact", "subnet_url", "discord", "description"}


async def find_exact_block(
    subtensor: AsyncSubtensor,
    netuid: int,
    field: str,
    old_val: str,
    new_val: str,
    high: int,
    low: int,
) -> int:
    """
    Binary search between high (gdzie już jest new_val)
    i low (gdzie jeszcze była old_val).
    Zwraca minimalny blok, w którym entry.field == new_val.
    """
    left, right = high, low
    while left - right > 1:
        mid = (left + right) // 2
        try:
            infos = await subtensor.all_subnets(block_number=mid)
            info_map = {i.netuid: i for i in infos}
            ent = info_map.get(netuid)
            if not ent:
                curr = old_val
            else:
                if field in TOP_LEVEL:
                    curr = getattr(ent, field)
                else:
                    si = ent.subnet_identity
                    curr = getattr(si, field) if si else None
        except Exception:
            # jeśli RPC się rozsypie, załóż old_val i idź dalej
            curr = old_val

        if curr == new_val:
            left = mid
        else:
            right = mid

    return left


async def main():
    # 1) Wczytaj przybliżone zmiany
    changes = []
    with open("changes.csv", newline="", encoding="utf-8") as f:
        rdr = csv.DictReader(f)
        for r in rdr:
            changes.append(
                {
                    "netuid": int(r["netuid"]),
                    "field": r["parameter"],
                    "old": r["old_value"],
                    "new": r["new_value"],
                    "approx": int(r["block_number"]),
                }
            )

    # 2) Połącz się raz
    subtensor = await get_async_subtensor("archive", log_verbose=False)

    # 3) Otwórz plik wynikowy
    with open("changes_exact.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["netuid", "parameter", "old_value", "new_value", "exact_block"])

        # 4) Dla każdej zmiany – binsearch
        for ch in tqdm(changes, desc="Refining"):
            high = ch["approx"]
            low = ch["approx"] - STEP
            exact = await find_exact_block(
                subtensor, ch["netuid"], ch["field"], ch["old"], ch["new"], high, low
            )
            w.writerow([ch["netuid"], ch["field"], ch["old"], ch["new"], exact])

    print("Gotowe: changes_exact.csv")


if __name__ == "__main__":
    asyncio.run(main())

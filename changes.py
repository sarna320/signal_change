from tqdm import tqdm
import asyncio
import csv
from bittensor.core.async_subtensor import get_async_subtensor, AsyncSubtensor
from typing import Dict


async def fetch_snapshot(
    subtensor: AsyncSubtensor,
    block_number: int,
    semaphore: asyncio.Semaphore,
    snapshots: Dict[int, dict],
):
    """
    Fetches all_subnets at a given block_number under a semaphore limit.
    Stores dict(netuid -> DynamicInfo) in snapshots[block_number].
    """
    async with semaphore:
        try:
            infos = await subtensor.all_subnets(block_number=block_number)
            snapshots[block_number] = {info.netuid: info for info in infos}
        except Exception as e:
            print(f"⚠️ Block {block_number} failed: {e}")
            snapshots[block_number] = {}


async def main():
    # Connect to the archive
    subtensor = await get_async_subtensor("archive", log_verbose=False)

    # Define block range
    latest_block = await subtensor.get_current_block()
    END = latest_block
    DAYS_BACK = 60
    START = END - (60 * 60 * 24 * DAYS_BACK) // 12  # 1 block = 12s
    CONCURRENCY = 1  # Max concurrent RPCs
    STEPS = 100

    print(f"Comparing from block {END} down to {START}")

    # Build descending block list
    blocks = list(range(END, START - 1, -STEPS))
    snapshots: Dict[int, dict] = {}
    semaphore = asyncio.Semaphore(CONCURRENCY)

    # Fetch snapshots in parallel
    tasks = [fetch_snapshot(subtensor, blk, semaphore, snapshots) for blk in blocks]
    for fut in tqdm(
        asyncio.as_completed(tasks), total=len(tasks), desc="Fetching snapshots"
    ):
        await fut

    # Prepare CSV
    output_path = "./changes.csv"
    with open(output_path, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(
            ["block_number", "netuid", "parameter", "old_value", "new_value"]
        )

        # Compare pairs: prev_map from a higher block, curr_map from a lower block
        prev_map = snapshots.get(blocks[0], {})
        for blk in tqdm(blocks[1:], desc="Comparing snapshots"):
            curr_map = snapshots.get(blk, {})
            for netuid, prev_info in prev_map.items():
                curr_info = curr_map.get(netuid)
                if not curr_info:
                    continue
                # Top-level fields
                for attr in ["owner_hotkey", "owner_coldkey", "subnet_name"]:
                    old = getattr(prev_info, attr)
                    new = getattr(curr_info, attr)
                    if old != new:
                        writer.writerow([blk, netuid, attr, old, new])
                # SubnetIdentity fields
                old_id = prev_info.subnet_identity
                new_id = curr_info.subnet_identity
                for id_attr in [
                    "github_repo",
                    "subnet_contact",
                    "subnet_url",
                    "discord",
                    "description",
                ]:
                    old_val = getattr(old_id, id_attr) if old_id else None
                    new_val = getattr(new_id, id_attr) if new_id else None
                    if old_val != new_val:
                        writer.writerow([blk, netuid, id_attr, old_val, new_val])
            # Shift prev_map downward
            prev_map = curr_map

    print(f"Change log written to {output_path}")


if __name__ == "__main__":
    asyncio.run(main())

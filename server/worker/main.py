from __future__ import annotations

import asyncio


async def main() -> None:
    # placeholder; keeps the
    # container alive so the service stays up under compose.
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(main())

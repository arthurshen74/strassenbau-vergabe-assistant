from __future__ import annotations

import asyncio


async def main() -> None:
    # Placeholder until task 10 wires the ingest queue consumer; keeps the
    # container alive so the service stays up under compose.
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(main())

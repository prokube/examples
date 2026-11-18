"""The worker as a container in the workspace: connect() needs no login there."""

import asyncio

from prokube.workflows import connect
from temporalio.worker import Worker

from activities import send_a2a_message
from workflows import ResearchWithApproval

TASK_QUEUE = "agent-approval"


async def main() -> None:
    client = await connect()
    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[ResearchWithApproval],
        activities=[send_a2a_message],
    )
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())

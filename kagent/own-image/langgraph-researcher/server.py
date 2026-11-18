"""Serve the graph over kagent's private A2A gRPC contract."""

import asyncio
import json

import grpc
from a2a.server.request_handlers.grpc_handler import GrpcHandler
from a2a.types import AgentCard, a2a_pb2, a2a_pb2_grpc
from google.protobuf.json_format import ParseDict
from grpc_health.v1 import health, health_pb2, health_pb2_grpc
from kagent.core import AsyncControllerClient, KAgentConfig, materialize_from_bootstrap
from kagent.core.a2a import (
    KAgentGrpcServerCallContextBuilder,
    KAgentRequestContextBuilder,
)
from kagent.core.a2a._task_store import KAgentRequestHandler, KAgentTaskStore
from kagent.langgraph import LangGraphAgentExecutor

from agent import graph


async def readyz(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    request = await reader.readline()
    status = b"200 OK" if request.startswith(b"GET /readyz ") else b"404 Not Found"
    writer.write(b"HTTP/1.1 " + status + b"\r\nContent-Length: 2\r\n\r\nOK")
    await writer.drain()
    writer.close()


async def main() -> None:
    # Fetch this revision's configuration and Agent Card from the controller.
    materialize_from_bootstrap("/config")
    config = KAgentConfig.from_file("/config/config.json")
    with open("/config/agent-card.json", encoding="utf-8") as file:
        card = ParseDict(json.load(file), AgentCard())

    async with AsyncControllerClient(config.api_url, agent_name=config.app_name) as controller:
        # Tasks are stored by the controller, not in this process.
        task_store = KAgentTaskStore(controller)
        handler = KAgentRequestHandler(
            agent_executor=LangGraphAgentExecutor(graph=graph, app_name=config.app_name),
            task_store=task_store,
            agent_card=card,
            request_context_builder=KAgentRequestContextBuilder(task_store=task_store),
        )

        server = grpc.aio.server()
        a2a_pb2_grpc.add_A2AServiceServicer_to_server(
            GrpcHandler(handler, context_builder=KAgentGrpcServerCallContextBuilder()), server
        )
        health_service = health.aio.HealthServicer()
        service = a2a_pb2.DESCRIPTOR.services_by_name["A2AService"].full_name
        await health_service.set(service, health_pb2.HealthCheckResponse.SERVING)
        health_pb2_grpc.add_HealthServicer_to_server(health_service, server)
        server.add_insecure_port(f"[::]:{config.runtime.port or 80}")
        await server.start()

        await asyncio.start_server(readyz, port=8081)
        await server.wait_for_termination()


if __name__ == "__main__":
    asyncio.run(main())

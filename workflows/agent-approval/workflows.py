"""An Agent researches a topic, a person approves, the Agent summarises.

Approvals follow Temporal's approval pattern: the workflow waits with
wait_condition, the decision arrives as an Update with a validator, a Query
returns the open question, and Search Attribute ApprovalStatus=Pending lets UIs
list runs that wait. Tool approvals an Agent asks for become approvals of the
run the same way.
"""

from dataclasses import dataclass
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy, SearchAttributeKey

with workflow.unsafe.imports_passed_through():
    from activities import A2AMessage, A2AResult, send_a2a_message

APPROVAL_STATUS = SearchAttributeKey.for_keyword("ApprovalStatus")
APPROVAL_TIMEOUT = timedelta(days=7)


@dataclass
class ResearchRequest:
    topic: str
    agent: str = "research-assistant"


@dataclass
class PendingApproval:
    id: str
    step: str
    question: str


@dataclass
class ApprovalDecision:
    approved: bool
    approver: str = ""
    comment: str = ""
    # Which question this answers; a decision for an older one is rejected.
    approval_id: str = ""


@dataclass
class ResearchResult:
    approved: bool
    research: str
    summary: str = ""


@workflow.defn
class ResearchWithApproval:
    def __init__(self) -> None:
        self.pending: PendingApproval | None = None
        self.decision: ApprovalDecision | None = None
        self.count = 0

    @workflow.run
    async def run(self, request: ResearchRequest) -> ResearchResult:
        research = await self.ask("research", request.agent,
                                  f"Research briefly and cite your sources: {request.topic}")
        review = await self.approval("review", f"Publish this research?\n\n{research}")
        if not review.approved:
            return ResearchResult(approved=False, research=research)
        summary = await self.ask("summary", request.agent,
                                 f"Summarise this text in three short bullet points, without fetching anything:\n\n{research}")
        return ResearchResult(approved=True, research=research, summary=summary)

    async def ask(self, step: str, agent: str, text: str) -> str:
        """Ask an Agent; its tool approvals become approvals of this run."""
        message = A2AMessage(agent=agent, message_id=str(workflow.uuid4()), text=text)
        answers: list[str] = []
        while True:
            result: A2AResult = await workflow.execute_activity(
                send_a2a_message, message,
                start_to_close_timeout=timedelta(minutes=15),
                heartbeat_timeout=timedelta(seconds=60),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
            if result.text:
                answers.append(result.text)
            if result.state != "input_required" or not result.tool_approvals:
                return "\n\n".join(answers)
            tools = "; ".join(f"{t.name}({', '.join(f'{k}={v}' for k, v in t.args.items())})"
                              for t in result.tool_approvals)
            decision = await self.approval(step, f"{agent} wants to run: {tools}")
            message = A2AMessage(
                agent=agent, message_id=str(workflow.uuid4()), task_id=result.task_id,
                context_id=result.context_id, approvals={t.id: decision.approved for t in result.tool_approvals},
            )

    async def approval(self, step: str, question: str) -> ApprovalDecision:
        self.count += 1
        self.pending = PendingApproval(id=f"{step}-{self.count}", step=step, question=question)
        self.decision = None
        workflow.upsert_search_attributes([APPROVAL_STATUS.value_set("Pending")])
        workflow.set_current_details(f"**Waiting for approval** ({step})\n\n{question}")
        try:
            await workflow.wait_condition(lambda: self.decision is not None, timeout=APPROVAL_TIMEOUT)
        except TimeoutError:
            self.decision = ApprovalDecision(approved=False, comment="No decision in time")
        decision = self.decision
        self.pending = None
        workflow.upsert_search_attributes([APPROVAL_STATUS.value_unset()])
        workflow.set_current_details(
            f"{'Approved' if decision.approved else 'Rejected'} ({step}) by {decision.approver or 'unknown'}"
        )
        return decision

    @workflow.update
    def approve(self, decision: ApprovalDecision) -> str:
        self.decision = decision
        return "approved" if decision.approved else "rejected"

    @approve.validator
    def validate_approve(self, decision: ApprovalDecision) -> None:
        if self.pending is None:
            raise ValueError("Nothing is waiting for approval")
        if decision.approval_id and decision.approval_id != self.pending.id:
            raise ValueError(f"Approval {decision.approval_id} is no longer open")

    @workflow.query
    def pending_approval(self) -> PendingApproval | None:
        return self.pending

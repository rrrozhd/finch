"""Chat agent over the fact store and engine. It reads freely; every change it proposes waits for the user's approval."""
from datetime import date

from deepagents import create_deep_agent
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from . import facts, llm, pipeline, sandbox

CATEGORIES = ("income", "business_expense", "personal", "transfer", "tax_payment")
PROMPT = """You are a quarterly-tax copilot for a NYC freelancer. Use your tools to answer questions about their 2026
estimated taxes. Rules:
- Never state a dollar figure that a tool did not return. All math comes from the engine (get_summary / what_if).
- To change how a transaction is categorized, call recategorize. The user must approve it before it takes effect.
- You never pay, file or submit anything. Payments are made by the user via the pay links.
- Cite the transaction keys or sources behind your answers. Keep answers short, in plain text (no markdown)."""
_memory = MemorySaver()  # shortcut: in-process, so chat threads are lost on restart; fine for the demo


def _tools(session: str):
    def get_summary() -> dict:
        """Current computed result: net profit, annual federal/NY/NYC tax, next installment due and amount, inputs."""
        r = pipeline.results(session)
        r.pop("sources")  # every transaction; use find_transactions instead
        return r

    def find_transactions(query: str = "", category: str = "") -> list[dict]:
        """Search current transactions by description substring and/or category
        (income, business_expense, personal, transfer, tax_payment). Returns at most 20 rows."""
        rows = [dict(key=k, source=v["source"], by=v["by"], **v["value"]) for k, v in facts.current(session, "txn:").items()
                if query.lower() in v["value"]["description"].lower() and (not category or v["value"]["category"] == category)]
        return rows[:20]

    def fact_history(key: str) -> list[dict]:
        """Every version of a fact (e.g. 'txn:42'), oldest first, with who wrote it and why. Superseded facts are kept."""
        return facts.history(session, key)

    def what_if(extra_income: float = 0, extra_expenses: float = 0) -> dict:
        """Recompute taxes with hypothetical extra income and/or extra deductible expenses. Changes nothing."""
        f = dict(pipeline.results(session)["inputs"])
        f["gross_income"] += extra_income
        f["deductible_expenses"] += extra_expenses
        return sandbox.compute(f, date.today())

    def recategorize(key: str, category: str, business_pct: int, reason: str) -> dict:
        """Change a transaction's category (requires user approval). business_pct is the deductible percent, 0-100."""
        if category not in CATEGORIES or not 0 <= business_pct <= 100 or not facts.current(session, key).get(key):
            return dict(error="invalid category, percent or key")
        return pipeline.correct(session, key, category, business_pct, None, reason)

    return [get_summary, find_transactions, fact_history, what_if, recategorize]


def _agent(session: str):
    return create_deep_agent(model=llm.chat(llm.SMART), tools=_tools(session), system_prompt=PROMPT,
                             interrupt_on={"recategorize": True}, checkpointer=_memory)


def _reply(r: dict) -> dict:
    if r.get("__interrupt__"):
        return dict(pending=[dict(tool=a["name"], args=a["args"]) for a in r["__interrupt__"][0].value["action_requests"]])
    return dict(reply=r["messages"][-1].content)


def chat(session: str, text: str) -> dict:
    return _reply(_agent(session).invoke({"messages": [{"role": "user", "content": text}]},
                                         {"configurable": {"thread_id": session}}))


def resume(session: str, approve: bool) -> dict:
    """One approve/reject covers every change the agent proposed in this step (it may batch parallel tool calls)."""
    a, cfg = _agent(session), {"configurable": {"thread_id": session}}
    n = len(a.get_state(cfg).interrupts[0].value["action_requests"])
    d = {"type": "approve"} if approve else {"type": "reject", "message": "The user rejected this change."}
    return _reply(a.invoke(Command(resume={"decisions": [d] * n}), cfg))

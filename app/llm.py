"""The only places an LLM is used: categorizing what rules can't, vision fallback for bad receipts,
wording questions and parsing answers. Every output is validated by Pydantic before it becomes a fact."""
import base64
import os
from functools import lru_cache
from typing import Literal, Optional

from botocore.exceptions import ClientError
from langchain_aws import ChatBedrockConverse
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

SMART = os.getenv("BEDROCK_MODEL_SMART", "us.anthropic.claude-sonnet-5-5")  # deductibility decisions + receipt vision
FAST = os.getenv("BEDROCK_MODEL_FAST", "us.anthropic.claude-haiku-5-5")  # wording questions, parsing answers


@lru_cache(maxsize=None)
def chat(model: str) -> ChatBedrockConverse:
    """Bedrock via LangChain. Auth: BEDROCK_API_KEY (boto3 reads it as AWS_BEARER_TOKEN_BEDROCK), else AWS access keys."""
    key = (os.getenv("BEDROCK_API_KEY") or "").removeprefix("bedrock:")  # console copy can include a "bedrock:" label
    if key:
        os.environ.setdefault("AWS_BEARER_TOKEN_BEDROCK", key)
    return ChatBedrockConverse(model=model, region_name=os.getenv("AWS_REGION", "us-west-2"), max_tokens=8000,
                               additional_model_request_fields={"output_config": {"effort": "low"}})


def _wire_schema(node):
    """Bedrock structured output rejects numeric bounds; Pydantic still enforces them on the way back."""
    if isinstance(node, dict):
        return {k: _wire_schema(v) for k, v in node.items() if k not in ("minimum", "maximum")}
    return [_wire_schema(v) for v in node] if isinstance(node, list) else node


def _parse(schema, prompt, content=None, model=SMART):
    msg = HumanMessage(content=(content or []) + [{"type": "text", "text": prompt}])
    wire = {"title": schema.__name__, **_wire_schema(schema.model_json_schema())}
    runnable = chat(model).with_structured_output(wire, method="json_schema")
    if model != SMART:  # Bedrock marketplace access for the fast model has been intermittent: fall back to the smart model
        runnable = runnable.with_fallbacks([chat(SMART).with_structured_output(wire, method="json_schema")],
                                           exceptions_to_handle=(ClientError,))
    out = runnable.invoke([msg])
    if out is None:
        raise ValueError("LLM gave no valid output")
    return schema.model_validate(out)


SCHED_C = ["Advertising", "Contract labor", "Depreciation / Section 179 (equipment)", "Meals (50%)",
           "Rent (coworking)", "Software / subscriptions", "Supplies", "Travel", "Utilities (phone)", "Other business expense"]


class Cat(BaseModel):
    merchant: str
    category: Literal["income", "business_expense", "personal", "transfer", "tax_payment"]
    schedule_c_category: Optional[Literal[tuple(SCHED_C)]] = None
    business_pct: int = Field(ge=0, le=100, description="if it turns out to be business: the deductible percent")
    ask_user: bool = Field(description="true when only the taxpayer can know (e.g. a restaurant could be a client meal)")
    why: str


class Cats(BaseModel):
    items: list[Cat]


def categorize(merchants: list[dict], line_of_work: str) -> dict[str, Cat]:
    """merchants: [{merchant, examples:[amounts], has_receipt, receipt_items}] -> {merchant: Cat}. One call per batch."""
    if not merchants:
        return {}
    lines = "\n".join(f"- {m['merchant']} | amounts: {m['examples'][:4]} | receipt: {m.get('receipt_items') or 'none'}"
                      for m in merchants)
    out = _parse(Cats, f"""You categorize bank transactions for a US self-employed taxpayer ({line_of_work}, files Schedule C).
For each merchant decide: category; if business_expense, the Schedule C category and the business-use percent
(meals with clients are 50%; a personal phone used for work is partly business; groceries, rent on a home, gym,
streaming and food delivery are personal unless a receipt shows otherwise). A matching receipt with business items is
strong evidence of a business expense. Do not guess facts only the taxpayer knows: if a merchant (restaurants, bars,
cafes) could be business depending on who was there, set ask_user=true and fill schedule_c_category/business_pct with
what applies if it was business. Return one item per merchant, merchant string copied exactly.

{lines}""")
    return {c.merchant: c for c in out.items}


class ReceiptRead(BaseModel):
    vendor: str
    date: str = Field(description="YYYY-MM-DD")
    total: float
    items: list[str]


def read_receipt(image: bytes, media_type: str) -> ReceiptRead:
    img = {"type": "image", "base64": base64.standard_b64encode(image).decode(), "mime_type": media_type}
    return _parse(ReceiptRead, "Read this receipt. Return vendor, purchase date, the grand total, and the line items.", [img])


class Parsed(BaseModel):
    ok: bool
    value: Optional[str] = Field(None, description="normalized value as a string, numbers without $ or commas")
    clarify: Optional[str] = Field(None, description="if not ok, a short follow-up question")


@lru_cache(maxsize=64)
def word_question(field: str, hint: str) -> str:
    class Q(BaseModel):
        question: str
    return _parse(Q, f"Write one short, friendly question asking a freelancer for: {hint}. No preamble.", model=FAST).question


def parse_answer(field: str, hint: str, answer: str) -> Parsed:
    return _parse(Parsed, f"""Field: {field} ({hint}). User answered: {answer!r}.
If the answer gives the value, set ok=true and value normalized (dollar amounts as plain numbers, yes/no as 'yes'/'no',
filing status as one of single/married_joint/married_separate/head_of_household, state as 2-letter code). Otherwise ok=false.""",
                  model=FAST)

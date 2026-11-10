"""The flow document: the single source of truth for a ScrapeOnce workflow.

Every save, agent edit and publish goes through these models. They are strict on purpose:
unknown keys are rejected, node types / field types / condition operators come from fixed
lists, selectors are length-limited and must parse, and there is no place for code, regex
or template strings. See docs/design.md ("Flow model") and specs/contracts.md (C1).
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StrictFloat,
    StrictInt,
    StringConstraints,
    field_validator,
    model_validator,
)
from pydantic_core import PydanticCustomError
from selectolax.lexbor import LexborHTMLParser

# ---------------------------------------------------------------------------
# Limits (kept in one place so docs, tests and code agree)
# ---------------------------------------------------------------------------
MAX_NODES = 30
MAX_EDGES = 100
MAX_VARIABLES = 20
MAX_FIELDS = 20
MAX_RULES = 10
MAX_SELECTOR_LEN = 200
MAX_URL_LEN = 2000
MAX_LIST_ITEMS = 25
MAX_TEXT_LEN = 200

_SELECTOR_PROBE = LexborHTMLParser("<html><body></body></html>")

# Field names that look like personal data are refused (FR-34). Matched on whole words of the
# snake_case name, so "seller_phone" is refused but "iphone_price" or "automobile" are not.
PII_NAME_WORDS = frozenset({
    "email", "mail", "phone", "mobile", "telephone", "tel", "whatsapp", "cnic", "nic", "ssn",
    "passport", "password", "address", "dob", "birthday", "birthdate",
})
PII_NAME_PAIRS = frozenset({("e", "mail"), ("date", "of", "birth"), ("phone", "number")})


def incomplete(message: str) -> PydanticCustomError:
    """A setting the user hasn't filled in yet. Allowed in a saved draft, refused at dry run and
    publish. Use ValueError instead for anything that is WRONG rather than just not done yet."""
    return PydanticCustomError("incomplete", message)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# ---------------------------------------------------------------------------
# Reusable constrained types
# ---------------------------------------------------------------------------
def _check_selector(value: str) -> str:
    try:
        _SELECTOR_PROBE.css(value)
    except Exception as exc:  # selectolax raises SelectolaxError on a bad selector
        raise ValueError("Selector does not parse") from exc
    return value


def _check_http_url(value: str) -> str:
    if any(ch.isspace() or ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise ValueError("URL may not contain spaces or control characters")
    try:
        parts = urlsplit(value)
    except ValueError as exc:  # e.g. an unclosed IPv6 bracket
        raise ValueError("URL is not valid") from exc
    if parts.scheme not in ("http", "https"):
        raise ValueError("Only http and https URLs are allowed")
    if not parts.hostname:
        raise ValueError("URL has no host")
    if parts.username or parts.password:
        raise ValueError("URLs with credentials are not allowed")
    return value


def _check_safe_text(value: str) -> str:
    # Labels are shown in the UI; React escapes them, but we still refuse markup and
    # template syntax so nothing that looks like code is ever stored.
    if any(ch in value for ch in "<>{}`"):
        raise ValueError("Text may not contain < > { } or backticks")
    return value


def _check_timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"Unknown timezone {value!r}") from exc
    return value


Selector = Annotated[
    str,
    StringConstraints(min_length=1, max_length=MAX_SELECTOR_LEN),
    AfterValidator(_check_selector),
]
HttpUrlStr = Annotated[
    str, StringConstraints(min_length=1, max_length=MAX_URL_LEN), AfterValidator(_check_http_url)
]
Name = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,39}$")]
NodeId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,32}$")]
AttrName = Annotated[str, StringConstraints(pattern=r"^[A-Za-z_:][-A-Za-z0-9_:.]{0,39}$")]
Label = Annotated[
    str, StringConstraints(min_length=1, max_length=80), AfterValidator(_check_safe_text)
]
TimeOfDay = Annotated[str, StringConstraints(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")]
Timezone = Annotated[str, AfterValidator(_check_timezone)]

FieldType = Literal["text", "price", "int", "url", "date", "stock"]
VariableType = Literal["text", "number", "price", "boolean", "url", "url_list", "text_list"]


class VarRef(Strict):
    """A reference to a flow variable: {"var": "name"}. Never a template string."""

    var: Name


# ---------------------------------------------------------------------------
# Variables
# ---------------------------------------------------------------------------
def _to_decimal(value: Any) -> Decimal:
    if isinstance(value, bool):
        raise ValueError("Expected a number, got a boolean")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{value!r} is not a number") from exc
    if not result.is_finite():
        raise ValueError("Number must be finite")
    return result


class Variable(Strict):
    name: Name
    type: VariableType
    value: Any

    @model_validator(mode="after")
    def _check_value(self) -> Variable:
        v = self.value
        if self.type == "text":
            if not isinstance(v, str) or len(v) > MAX_TEXT_LEN:
                raise ValueError(f"text variable must be a string of at most {MAX_TEXT_LEN} characters")
        elif self.type == "number":
            self.value = str(_to_decimal(v))
        elif self.type == "price":
            d = _to_decimal(v)
            if d <= 0:
                raise ValueError("price variable must be greater than 0")
            self.value = str(d)
        elif self.type == "boolean":
            if not isinstance(v, bool):
                raise ValueError("boolean variable must be true or false")
        elif self.type == "url":
            if not isinstance(v, str):
                raise ValueError("url variable must be a string")
            _check_http_url(v)
        elif self.type in ("url_list", "text_list"):
            if not isinstance(v, list) or not 1 <= len(v) <= MAX_LIST_ITEMS:
                raise ValueError(f"{self.type} must have 1 to {MAX_LIST_ITEMS} entries")
            cleaned: list[str] = []
            for item in v:
                if not isinstance(item, str) or not item.strip():
                    raise ValueError(f"{self.type} entries must be non-empty strings")
                item = item.strip()
                if self.type == "url_list":
                    if len(item) > MAX_URL_LEN:
                        raise ValueError("URL is too long")
                    _check_http_url(item)
                elif len(item) > MAX_TEXT_LEN:
                    raise ValueError(f"text_list entries must be at most {MAX_TEXT_LEN} characters")
                if item not in cleaned:  # de-duplicate, keep order
                    cleaned.append(item)
            self.value = cleaned
        return self


# ---------------------------------------------------------------------------
# Shared pieces of node configs
# ---------------------------------------------------------------------------
class FieldSpec(Strict):
    name: Name
    selector: Selector
    attr: AttrName | None = None
    type: FieldType
    required: bool = False

    @model_validator(mode="after")
    def _no_pii(self) -> FieldSpec:
        if looks_like_pii(self.name):
            raise ValueError(f"Field name {self.name!r} looks like personal data and is not allowed")
        return self


def looks_like_pii(name: str) -> bool:
    words = tuple(w for w in name.lower().split("_") if w)
    if any(w in PII_NAME_WORDS for w in words):
        return True
    return any(words[i:i + len(pair)] == pair for pair in PII_NAME_PAIRS for i in range(len(words)))


def _unique_field_names(fields: list[FieldSpec]) -> list[FieldSpec]:
    names = [f.name for f in fields]
    dupes = sorted({n for n in names if names.count(n) > 1})
    if dupes:
        raise ValueError(f"Duplicate field names: {', '.join(dupes)}")
    return fields


Fields = Annotated[
    list[FieldSpec],
    Field(min_length=1, max_length=MAX_FIELDS),
    AfterValidator(_unique_field_names),
]


class CountRange(Strict):
    min: int = Field(ge=0, le=500)
    max: int = Field(ge=1, le=500)

    @model_validator(mode="after")
    def _ordered(self) -> CountRange:
        if self.max < self.min:
            raise ValueError("expected_count.max must be >= min")
        return self


# Condition operators, grouped by what they work on (design.md "Condition rules").
NUMERIC_OPS = ("lt", "lte", "gt", "gte", "eq", "neq")
TEXT_OPS = ("eq", "neq", "contains", "not_contains")
PRESENCE_OPS = ("is_empty", "not_empty")
ITEM_CHANGE_OPS = ("is_new", "is_removed")  # field must be "change"
FIELD_CHANGE_OPS = ("changed", "increased", "decreased", "drop_pct_gt", "rise_pct_gt")
STOCK_OPS = ("in_stock", "out_of_stock", "back_in_stock")

Op = Literal[
    "lt", "lte", "gt", "gte", "eq", "neq", "contains", "not_contains", "is_empty", "not_empty",
    "is_new", "is_removed", "changed", "increased", "decreased", "drop_pct_gt", "rise_pct_gt",
    "in_stock", "out_of_stock", "back_in_stock",
]
OPS_NEEDING_VALUE = set(NUMERIC_OPS) | set(TEXT_OPS) | {"drop_pct_gt", "rise_pct_gt"}
OPS_NEEDING_HISTORY = set(ITEM_CHANGE_OPS) | set(FIELD_CHANGE_OPS) | {"back_in_stock"}

# Strict number types: a JSON true/false must not sneak in as 1/0, and NaN/Infinity are refused.
RuleValue = (
    Annotated[str, StringConstraints(max_length=MAX_TEXT_LEN)]
    | StrictInt
    | Annotated[StrictFloat, Field(allow_inf_nan=False)]
    | VarRef
)


class Rule(Strict):
    field: Name
    op: Op
    value: RuleValue | None = None

    @field_validator("value", mode="before")
    @classmethod
    def _no_booleans(cls, v: Any) -> Any:
        if isinstance(v, bool):
            raise ValueError("Value must be a number, text or a variable, not true/false")
        return v

    @model_validator(mode="after")
    def _value_matches_op(self) -> Rule:
        if self.op in OPS_NEEDING_VALUE and self.value is None:
            raise incomplete(f"Operator {self.op!r} needs a value")
        if self.op not in OPS_NEEDING_VALUE and self.value is not None:
            raise ValueError(f"Operator {self.op!r} does not take a value")
        if self.op in ITEM_CHANGE_OPS and self.field != "change":
            raise ValueError(f"Operator {self.op!r} only works on the field 'change'")
        if self.field == "change" and self.op not in ITEM_CHANGE_OPS:
            raise ValueError("The field 'change' only supports is_new and is_removed")
        if isinstance(self.value, str):
            _check_safe_text(self.value)
        return self


# ---------------------------------------------------------------------------
# Node configs
# ---------------------------------------------------------------------------
class TriggerConfig(Strict):
    mode: Literal["manual", "interval", "daily"] = "manual"
    every_minutes: int | None = Field(default=None, ge=1, le=1440)
    at_time: TimeOfDay | None = None
    timezone: Timezone = "Asia/Karachi"

    @model_validator(mode="after")
    def _mode_fields(self) -> TriggerConfig:
        if self.mode == "interval" and self.every_minutes is None:
            raise incomplete("interval mode needs every_minutes")
        if self.mode == "daily" and self.at_time is None:
            raise incomplete("daily mode needs at_time (HH:MM)")
        return self


class FetchPageConfig(Strict):
    url: HttpUrlStr | VarRef


class PaginateConfig(Strict):
    next_selector: Selector
    max_pages: int = Field(default=3, ge=1, le=5)


class ExtractListConfig(Strict):
    base_selector: Selector
    fields: Fields
    identity_key: Name
    page_anchor: Selector | None = None
    expected_count: CountRange | None = None

    @model_validator(mode="after")
    def _identity_is_a_required_field(self) -> ExtractListConfig:
        field = next((f for f in self.fields if f.name == self.identity_key), None)
        if field is None:
            raise ValueError(f"identity_key {self.identity_key!r} must be one of the fields")
        # An item without its identity can't be tracked, so the identity field is always required.
        # Normalised here (and saved that way) rather than rejected, so the user isn't blocked.
        field.required = True
        return self


class ForEachConfig(Strict):
    source: Literal["items"] | VarRef = "items"
    max_items: int = Field(default=25, ge=1, le=MAX_LIST_ITEMS)
    on_error: Literal["skip", "stop"] = "skip"


class FetchItemPageConfig(Strict):
    url_field: Name = "url"


class ExtractFieldsConfig(Strict):
    fields: Fields


class ConditionConfig(Strict):
    match: Literal["all", "any"] = "all"
    rules: list[Rule] = Field(min_length=1, max_length=MAX_RULES)


class WaitConfig(Strict):
    seconds: Annotated[int | float, Field(ge=1, le=10)] | VarRef = 2


class CheckPageConfig(Strict):
    pass


class SaveRecordsConfig(Strict):
    dataset: Name
    identity_key: Name | None = None
    track_fields: list[Name] = Field(min_length=1, max_length=MAX_FIELDS)
    alert_on_first_run: bool = False


class AlertConfig(Strict):
    title: Label
    level: Literal["info", "warning"] = "info"


class ResultsConfig(Strict):
    name: Label


# Browser nodes: visible in the palette, rejected at publish (FR-27).
class ClickConfig(Strict):
    selector: Selector


class ScrollConfig(Strict):
    times: int = Field(default=1, ge=1, le=10)


class TypeTextConfig(Strict):
    selector: Selector
    text: Annotated[str, StringConstraints(max_length=MAX_TEXT_LEN), AfterValidator(_check_safe_text)]


class WaitForElementConfig(Strict):
    selector: Selector
    timeout_seconds: int = Field(default=5, ge=1, le=10)


# ---------------------------------------------------------------------------
# Nodes and edges
# ---------------------------------------------------------------------------
class Position(Strict):
    x: float = 0
    y: float = 0


class NodeBase(Strict):
    id: NodeId
    parentId: NodeId | None = None  # noqa: N815 - React Flow's name, kept as-is
    position: Position = Field(default_factory=Position)


class TriggerNode(NodeBase):
    type: Literal["trigger"]
    config: TriggerConfig = Field(default_factory=TriggerConfig)


class FetchPageNode(NodeBase):
    type: Literal["fetch_page"]
    config: FetchPageConfig


class PaginateNode(NodeBase):
    type: Literal["paginate"]
    config: PaginateConfig


class ExtractListNode(NodeBase):
    type: Literal["extract_list"]
    config: ExtractListConfig


class ForEachNode(NodeBase):
    type: Literal["for_each"]
    config: ForEachConfig = Field(default_factory=ForEachConfig)


class FetchItemPageNode(NodeBase):
    type: Literal["fetch_item_page"]
    config: FetchItemPageConfig = Field(default_factory=FetchItemPageConfig)


class ExtractFieldsNode(NodeBase):
    type: Literal["extract_fields"]
    config: ExtractFieldsConfig


class ConditionNode(NodeBase):
    type: Literal["condition"]
    config: ConditionConfig


class WaitNode(NodeBase):
    type: Literal["wait"]
    config: WaitConfig = Field(default_factory=WaitConfig)


class CheckPageNode(NodeBase):
    type: Literal["check_page"]
    config: CheckPageConfig = Field(default_factory=CheckPageConfig)


class SaveRecordsNode(NodeBase):
    type: Literal["save_records"]
    config: SaveRecordsConfig


class AlertNode(NodeBase):
    type: Literal["alert"]
    config: AlertConfig


class ResultsNode(NodeBase):
    type: Literal["results"]
    config: ResultsConfig


class ClickNode(NodeBase):
    type: Literal["click"]
    config: ClickConfig


class ScrollNode(NodeBase):
    type: Literal["scroll"]
    config: ScrollConfig = Field(default_factory=ScrollConfig)


class TypeTextNode(NodeBase):
    type: Literal["type"]
    config: TypeTextConfig


class WaitForElementNode(NodeBase):
    type: Literal["wait_for_element"]
    config: WaitForElementConfig


FlowNode = Annotated[
    TriggerNode | FetchPageNode | PaginateNode | ExtractListNode | ForEachNode | FetchItemPageNode
    | ExtractFieldsNode | ConditionNode | WaitNode | CheckPageNode | SaveRecordsNode | AlertNode
    | ResultsNode | ClickNode | ScrollNode | TypeTextNode | WaitForElementNode,
    Field(discriminator="type"),
]


class FlowEdge(Strict):
    id: NodeId
    source: NodeId
    target: NodeId
    sourceHandle: Literal["true", "false", "item", "done"] | None = None  # noqa: N815
    targetHandle: Literal["next"] | None = None  # noqa: N815


class Flow(Strict):
    version: int = Field(default=0, ge=0)
    variables: list[Variable] = Field(default_factory=list, max_length=MAX_VARIABLES)
    nodes: list[FlowNode] = Field(max_length=MAX_NODES)
    edges: list[FlowEdge] = Field(default_factory=list, max_length=MAX_EDGES)


# ---------------------------------------------------------------------------
# Node catalogue (palette + agent's list_node_types)
# ---------------------------------------------------------------------------
NODE_CATALOGUE: list[dict[str, Any]] = [
    {"type": "trigger", "group": "Trigger", "label": "Trigger", "model": TriggerConfig},
    {"type": "fetch_page", "group": "Source", "label": "Fetch Page", "model": FetchPageConfig},
    {"type": "paginate", "group": "Navigate", "label": "Paginate", "model": PaginateConfig},
    {"type": "extract_list", "group": "Extract", "label": "Extract List", "model": ExtractListConfig},
    {"type": "for_each", "group": "Control", "label": "For Each", "model": ForEachConfig},
    {"type": "fetch_item_page", "group": "Loop body", "label": "Fetch Item Page",
     "model": FetchItemPageConfig},
    {"type": "extract_fields", "group": "Loop body", "label": "Extract Fields",
     "model": ExtractFieldsConfig},
    {"type": "condition", "group": "Control", "label": "Condition", "model": ConditionConfig},
    {"type": "wait", "group": "Control", "label": "Wait", "model": WaitConfig},
    {"type": "check_page", "group": "Check", "label": "Check Page", "model": CheckPageConfig},
    {"type": "save_records", "group": "Store", "label": "Save Records", "model": SaveRecordsConfig},
    {"type": "alert", "group": "Output", "label": "Alert", "model": AlertConfig},
    {"type": "results", "group": "Output", "label": "Results", "model": ResultsConfig},
    {"type": "click", "group": "Browser", "label": "Click", "model": ClickConfig, "disabled": True},
    {"type": "scroll", "group": "Browser", "label": "Scroll", "model": ScrollConfig, "disabled": True},
    {"type": "type", "group": "Browser", "label": "Type", "model": TypeTextConfig, "disabled": True},
    {"type": "wait_for_element", "group": "Browser", "label": "Wait for Element",
     "model": WaitForElementConfig, "disabled": True},
]
BROWSER_NODE_TYPES = {e["type"] for e in NODE_CATALOGUE if e.get("disabled")}
LOOP_BODY_TYPES = {"fetch_item_page", "extract_fields", "condition", "wait"}


def node_type_schemas() -> list[dict[str, Any]]:
    return [
        {
            "type": e["type"],
            "group": e["group"],
            "label": e["label"],
            "disabled": bool(e.get("disabled")),
            "disabled_reason": "Needs a browser. Coming soon." if e.get("disabled") else None,
            "config_schema": e["model"].model_json_schema(),
        }
        for e in NODE_CATALOGUE
    ]

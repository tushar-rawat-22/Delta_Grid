"""Deterministic causal execution and Decimal accounting kernel for Mission 102."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, localcontext
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from .core import (
    ACCOUNTING_KERNEL_ID,
    FILL_MODEL_ID,
    INSTRUMENT_IDENTITY_ID,
    INTENT_SCHEMA_ID,
    POSITION_EFFECTIVE_TIME_ID,
    TARGET_EXPOSURE_MODEL_ID,
    DevelopmentRuntimeError,
    canonical_decimal,
    canonical_hash,
    decimal_text,
    parse_utc,
    m102_decimal_context,
    require_identifier,
)
from .loader import MarketEvent
from .registry import Adapter, VariantDefinition, canonical_instrument_id


MAX_EVENTS = 300_000
MAX_INTENTS = 100_000
MAX_FILLS = 100_000
MAX_ABS_DECIMAL = Decimal("1e30")
BPS = Decimal("10000")


def _utc_ms(value: str) -> int:
    parsed = parse_utc(value, "available_at")
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    delta = parsed - epoch
    total_microseconds = (
        delta.days * 86_400_000_000
        + delta.seconds * 1_000_000
        + delta.microseconds
    )
    # Ceil rather than floor so millisecond normalization can never make a
    # decision/fill effective before its exact evidence timestamp.
    return -(-total_microseconds // 1000)


@dataclass(frozen=True)
class TargetExposureIntent:
    symbol: str
    instrument_stream: str
    target_notional: str

    def __post_init__(self) -> None:
        require_identifier(self.symbol, "intent_symbol")
        if self.instrument_stream not in {"spot_ohlcv", "perpetual_ohlcv"}:
            raise DevelopmentRuntimeError("INSTRUMENT_NOT_TRADABLE")
        decimal_text(self.target_notional, "target_notional")

    def core(self) -> dict[str, Any]:
        return {
            "intent_schema": INTENT_SCHEMA_ID,
            "instrument_identity": INSTRUMENT_IDENTITY_ID,
            "instrument_id": canonical_instrument_id(self.instrument_stream, self.symbol),
            "symbol": self.symbol,
            "instrument_stream": self.instrument_stream,
            "target_notional": self.target_notional,
        }


@dataclass(frozen=True)
class RevealedEvent:
    event_id: str
    stream: str
    symbol: str
    interval: str | None
    event_time_ms: int
    available_at: str
    revision: int
    payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))


@dataclass
class _Pending:
    intent_id: str
    instrument_id: str
    symbol: str
    stream: str
    target_notional: Decimal
    target_notional_text: str
    decision_available_at: str
    decision_ms: int
    decision_event_id: str


class AccountingKernel:
    """Own every authoritative fill, position, cost, funding, and PnL value."""

    def __init__(self, variant: VariantDefinition, adapter: Adapter) -> None:
        self.variant = variant
        self.adapter = adapter
        self.initial_nav = Decimal(variant.initial_research_nav)
        self.cash = self.initial_nav
        self.positions: dict[str, Decimal] = {instrument_id: Decimal(0) for instrument_id in variant.tradable_instruments}
        self.position_history: dict[str, list[tuple[int, int, Decimal]]] = {instrument_id: [] for instrument_id in self.positions}
        self.last_prices: dict[str, Decimal] = {}
        self.pending: dict[str, _Pending] = {}
        self.fees = Decimal(0)
        self.slippage = Decimal(0)
        self.funding = Decimal(0)
        self.turnover = Decimal(0)
        self.peak_equity = self.initial_nav
        self.max_drawdown = Decimal(0)
        self.intent_count = 0
        self.fill_count = 0
        self._history_sequence = 0
        self.event_rows: list[dict[str, Any]] = []
        self.intent_rows: list[dict[str, Any]] = []
        self.fill_rows: list[dict[str, Any]] = []
        self.funding_rows: list[dict[str, Any]] = []
        self.accounting_rows: list[dict[str, Any]] = []

    def _bounded(self, *values: Decimal) -> None:
        if any(not item.is_finite() or abs(item) > MAX_ABS_DECIMAL for item in values):
            raise DevelopmentRuntimeError("ACCOUNTING_OVERFLOW")

    def _equity(self) -> Decimal:
        equity = self.cash
        for instrument_id, quantity in self.positions.items():
            price = self.last_prices.get(instrument_id)
            if price is not None:
                equity += quantity * price
        self._bounded(equity)
        return equity

    def _exposure(self) -> tuple[Decimal, Decimal]:
        values = [self.positions[instrument_id] * self.last_prices.get(instrument_id, Decimal(0)) for instrument_id in self.positions]
        return sum(map(abs, values), Decimal(0)), sum(values, Decimal(0))

    def _state_view(self) -> Mapping[str, Any]:
        gross, net = self._exposure()
        return MappingProxyType({
            "cash": canonical_decimal(self.cash),
            "equity": canonical_decimal(self._equity()),
            "positions": MappingProxyType({key: canonical_decimal(value) for key, value in sorted(self.positions.items())}),
            "gross_exposure": canonical_decimal(gross),
            "net_exposure": canonical_decimal(net),
            "pending_instruments": tuple(sorted(self.pending)),
            "revealed_event_count": len(self.event_rows),
        })

    def _position_at(self, instrument_id: str, economic_ms: int) -> Decimal:
        selected = Decimal(0)
        for event_ms, _sequence, quantity in self.position_history[instrument_id]:
            if event_ms <= economic_ms:
                selected = quantity
            else:
                break
        return selected

    def _mark(self, event: MarketEvent) -> None:
        instrument_id = canonical_instrument_id(event.stream, event.symbol)
        if instrument_id in self.positions and "close" in event.payload:
            self.last_prices[instrument_id] = Decimal(event.payload["close"])

    def _fund(self, event: MarketEvent) -> None:
        if event.stream != "funding_rates" or not self.variant.funding_accounting_applicable:
            return
        instrument_id = canonical_instrument_id("perpetual_ohlcv", event.symbol)
        if instrument_id not in self.positions:
            return
        economic_time = event.payload["funding_time_ms"]
        position = self._position_at(instrument_id, economic_time)
        rate = Decimal(event.payload["funding_rate"])
        mark = Decimal(event.payload["mark_price"])
        cash_flow = -(position * mark * rate)
        self.cash += cash_flow
        self.funding += cash_flow
        self._bounded(self.cash, self.funding)
        core = {
            "event_id": event.event_id, "instrument_id": instrument_id, "symbol": event.symbol,
            "economic_funding_time_ms": economic_time,
            "recognition_available_at": event.available_at,
            "position_at_economic_time": canonical_decimal(position),
            "funding_rate": event.payload["funding_rate"],
            "mark_price": event.payload["mark_price"],
            "cash_flow": canonical_decimal(cash_flow),
            "sign_convention": "POSITIVE_RATE_LONG_PAYS_SHORT_RECEIVES",
        }
        self.funding_rows.append({**core, "funding_transition_hash": canonical_hash(core)})

    def _fill_pending(self, event: MarketEvent) -> None:
        instrument_id = canonical_instrument_id(event.stream, event.symbol)
        pending = self.pending.get(instrument_id)
        if pending is None or "close_time_ms" not in event.payload:
            return
        close_time = event.payload["close_time_ms"]
        if close_time <= pending.decision_ms:
            return
        raw_price = Decimal(event.payload["close"])
        if not raw_price.is_finite() or raw_price <= 0:
            raise DevelopmentRuntimeError("EXECUTION_PRICE_INVALID")
        target_quantity_at_benchmark = pending.target_notional / raw_price
        delta = target_quantity_at_benchmark - self.positions[instrument_id]
        if pending.stream == "spot_ohlcv" and target_quantity_at_benchmark < 0:
            raise DevelopmentRuntimeError("SPOT_SHORT_FORBIDDEN")
        if delta == 0:
            # The pending target is deterministically resolved without
            # inventing a zero-quantity trade or transaction costs.
            del self.pending[instrument_id]
            return
        slip_rate = Decimal(self.variant.slippage_bps) / BPS
        execution_price = raw_price * (Decimal(1) + slip_rate if delta > 0 else Decimal(1) - slip_rate if delta < 0 else Decimal(1))
        if execution_price <= 0:
            raise DevelopmentRuntimeError("EXECUTION_PRICE_INVALID")
        execution_notional = abs(delta * execution_price)
        benchmark_notional = abs(delta * raw_price)
        fee = execution_notional * Decimal(self.variant.fee_bps) / BPS
        slippage_cost = abs(delta * (execution_price - raw_price))
        self.cash -= delta * execution_price + fee
        self.positions[instrument_id] = target_quantity_at_benchmark
        self.fees += fee
        self.slippage += slippage_cost
        self.turnover += benchmark_notional
        self.fill_count += 1
        if self.fill_count > MAX_FILLS:
            raise DevelopmentRuntimeError("FILL_COUNT_LIMIT")
        self._history_sequence += 1
        position_effective_at = max(close_time, _utc_ms(event.available_at))
        self.position_history[instrument_id].append((position_effective_at, self._history_sequence, target_quantity_at_benchmark))
        self.position_history[instrument_id].sort(key=lambda item: (item[0], item[1]))
        self._bounded(self.cash, target_quantity_at_benchmark, self.fees, self.slippage, self.turnover)
        core = {
            "fill_model": FILL_MODEL_ID,
            "target_exposure_model": TARGET_EXPOSURE_MODEL_ID,
            "position_effective_time_model": POSITION_EFFECTIVE_TIME_ID,
            "intent_id": pending.intent_id,
            "instrument_id": instrument_id,
            "symbol": event.symbol,
            "instrument_stream": pending.stream,
            "decision_available_at": pending.decision_available_at,
            "target_notional": pending.target_notional_text,
            "target_quantity_at_benchmark": canonical_decimal(target_quantity_at_benchmark),
            "benchmark_close_time_ms": close_time,
            "fill_evidence_available_at": event.available_at,
            "position_effective_at": position_effective_at,
            "fill_event_id": event.event_id,
            "benchmark_price": canonical_decimal(raw_price),
            "execution_price": canonical_decimal(execution_price),
            "execution_notional": canonical_decimal(execution_notional),
            "quantity_delta": canonical_decimal(delta),
            "position_after": canonical_decimal(target_quantity_at_benchmark),
            "fee": canonical_decimal(fee),
            "slippage_cost": canonical_decimal(slippage_cost),
        }
        self.fill_rows.append({**core, "fill_hash": canonical_hash(core)})
        del self.pending[instrument_id]

    def _validate_intent(self, intent: Any, event: MarketEvent, ordinal: int) -> _Pending:
        if type(intent) is not TargetExposureIntent:
            raise DevelopmentRuntimeError("INTENT_SCHEMA_INVALID")
        instrument_id = canonical_instrument_id(intent.instrument_stream, intent.symbol)
        if instrument_id not in self.variant.tradable_instruments:
            raise DevelopmentRuntimeError("INTENT_INSTRUMENT_UNAUTHORIZED")
        if instrument_id in self.pending:
            raise DevelopmentRuntimeError("PENDING_INTENT_CONFLICT")
        target = Decimal(intent.target_notional)
        bound = Decimal(self.variant.per_instrument_bounds[instrument_id])
        if abs(target) > bound:
            raise DevelopmentRuntimeError("INSTRUMENT_EXPOSURE_LIMIT")
        if intent.instrument_stream == "spot_ohlcv" and target < 0:
            raise DevelopmentRuntimeError("SPOT_SHORT_FORBIDDEN")
        targets = {}
        for key in self.positions:
            if key == instrument_id:
                targets[key] = target
            elif key in self.pending:
                targets[key] = self.pending[key].target_notional
            else:
                targets[key] = self.positions[key] * self.last_prices.get(key, Decimal(0))
        gross = sum(map(abs, targets.values()), Decimal(0))
        net = sum(targets.values(), Decimal(0))
        if gross > Decimal(self.variant.max_gross_research_exposure) or abs(net) > Decimal(self.variant.max_net_research_exposure):
            raise DevelopmentRuntimeError("RESEARCH_EXPOSURE_LIMIT")
        decision_ms = _utc_ms(event.available_at)
        core = {
            **intent.core(), "decision_event_id": event.event_id,
            "decision_available_at": event.available_at, "ordinal": ordinal,
        }
        intent_id = f"m102-intent-{canonical_hash(core)}"
        self.intent_rows.append({**core, "intent_id": intent_id, "intent_hash": canonical_hash(core)})
        return _Pending(intent_id, instrument_id, intent.symbol, intent.instrument_stream, target, intent.target_notional, event.available_at, decision_ms, event.event_id)

    def _account(self, event: MarketEvent) -> None:
        equity = self._equity()
        if equity > self.peak_equity:
            self.peak_equity = equity
        drawdown = self.peak_equity - equity
        if drawdown > self.max_drawdown:
            self.max_drawdown = drawdown
        gross, net = self._exposure()
        core = {
            "event_id": event.event_id,
            "cash": canonical_decimal(self.cash),
            "equity": canonical_decimal(equity),
            "gross_exposure": canonical_decimal(gross),
            "net_exposure": canonical_decimal(net),
            "peak_equity": canonical_decimal(self.peak_equity),
            "drawdown": canonical_decimal(drawdown),
        }
        self.accounting_rows.append({**core, "accounting_transition_hash": canonical_hash(core)})

    def run(self, events: Sequence[MarketEvent]) -> tuple[dict[str, Any], dict[str, Any]]:
        if len(events) > MAX_EVENTS:
            raise DevelopmentRuntimeError("EVENT_COUNT_LIMIT")
        with localcontext(m102_decimal_context()) as context:
            context.clear_flags()
            for event in events:
                if canonical_instrument_id(event.stream, event.symbol) not in self.variant.observable_inputs:
                    continue
                self._mark(event)
                self._fill_pending(event)
                self._fund(event)
                view = RevealedEvent(
                    event.event_id, event.stream, event.symbol, event.interval,
                    event.event_time_ms, event.available_at, event.revision, event.payload,
                )
                before = len(self.intent_rows)
                try:
                    produced = self.adapter.on_event(view, self._state_view())
                except DevelopmentRuntimeError:
                    raise
                except Exception as error:
                    raise DevelopmentRuntimeError("ADAPTER_FAILURE") from error
                if not isinstance(produced, Sequence) or isinstance(produced, (str, bytes, bytearray)):
                    raise DevelopmentRuntimeError("INTENT_SCHEMA_INVALID")
                for ordinal, intent in enumerate(produced, start=1):
                    self.intent_count += 1
                    if self.intent_count > MAX_INTENTS:
                        raise DevelopmentRuntimeError("INTENT_COUNT_LIMIT")
                    pending = self._validate_intent(intent, event, ordinal)
                    self.pending[pending.instrument_id] = pending
                self._account(event)
                event_core = {**event.identity(), "intent_count": len(self.intent_rows) - before}
                self.event_rows.append({**event_core, "reveal_hash": canonical_hash(event_core)})
            final_equity = self._equity()
            net_pnl = final_equity - self.initial_nav
            gross_pnl = net_pnl + self.fees + self.slippage - self.funding
            gross, net = self._exposure()
            metrics = {
                "initial_research_nav": canonical_decimal(self.initial_nav),
                "final_equity": canonical_decimal(final_equity),
                "gross_pnl": canonical_decimal(gross_pnl),
                "fees": canonical_decimal(self.fees),
                "slippage_costs": canonical_decimal(self.slippage),
                "funding_cash_flow": canonical_decimal(self.funding),
                "net_pnl": canonical_decimal(net_pnl),
                "turnover": canonical_decimal(self.turnover),
                "gross_exposure": canonical_decimal(gross),
                "net_exposure": canonical_decimal(net),
                "peak_equity": canonical_decimal(self.peak_equity),
                "max_drawdown": canonical_decimal(self.max_drawdown),
                "positions": {key: canonical_decimal(value) for key, value in sorted(self.positions.items())},
                "unfilled_intent_count": len(self.pending),
            }
            ledger_core = {
                "schema_version": "1.0", "ledger_type": "DELTAGRID_M102_EVENT_LEDGER_V1",
                "event_rows": self.event_rows, "intent_rows": self.intent_rows,
                "fill_rows": self.fill_rows, "funding_rows": self.funding_rows,
                "accounting_rows": self.accounting_rows,
            }
            ledger = {**ledger_core, "canonical_event_ledger_hash": canonical_hash(ledger_core)}
            return ledger, metrics

"""Static BTC-hedged alt residual-reversion family for RAB-1."""

from __future__ import annotations

from collections import deque
from decimal import Decimal, localcontext
from types import MappingProxyType
from typing import Any, Mapping

from offchain.research.development_runtime.core import canonical_decimal, m102_decimal_context
from offchain.research.development_runtime.kernel import TargetExposureIntent
from offchain.research.development_runtime.registry import FamilyDefinition, VariantDefinition


FAMILY_ID = "RAB1_BTC_HEDGED_ALT_RESIDUAL_REVERSION"
BTC = "BTCUSDT"
ALTS = ("ETHUSDT", "SOLUSDT")
LOOKBACKS = (168, 336)


class ResidualReversionAdapter:
    """Causal synchronized-hour Decimal residual-reversion adapter."""

    def __init__(self, parameters: Mapping[str, Any]) -> None:
        self.alt = str(parameters["alt_symbol"])
        self.lookback = int(parameters["estimation_hours"])
        self.beta_min = Decimal(str(parameters["beta_min"]))
        self.beta_max = Decimal(str(parameters["beta_max"]))
        self.entry_z = Decimal(str(parameters["entry_z"]))
        self.exit_z = Decimal(str(parameters["exit_z"]))
        self.max_holding_ms = int(parameters["maximum_holding_hours"]) * 3_600_000
        self.gross_cap = Decimal(str(parameters["gross_research_exposure"])
        )
        self.hour_prices: dict[int, dict[str, Decimal]] = {}
        self.previous_prices: dict[str, Decimal] | None = None
        self.returns: deque[tuple[Decimal, Decimal]] = deque(maxlen=self.lookback)
        self.residuals: deque[Decimal] = deque(maxlen=self.lookback)
        self.active_side = 0
        self.entered_at_ms: int | None = None
        self.last_processed_hour: int | None = None

    def _targets(self, side: int, beta: Decimal) -> list[TargetExposureIntent]:
        alt_notional = self.gross_cap / (Decimal(1) + abs(beta))
        btc_notional = -(Decimal(side) * alt_notional * beta)
        return [
            TargetExposureIntent(self.alt, "perpetual_ohlcv", canonical_decimal(Decimal(side) * alt_notional)),
            TargetExposureIntent(BTC, "perpetual_ohlcv", canonical_decimal(btc_notional)),
        ]

    def on_event(self, event: Any, state: Mapping[str, Any]):
        if event.stream != "perpetual_ohlcv" or event.symbol not in {BTC, self.alt}:
            return []
        close_time = event.payload.get("close_time_ms")
        close = event.payload.get("close")
        if type(close_time) is not int or not isinstance(close, str):
            return []
        price = Decimal(close)
        if not price.is_finite() or price <= 0:
            return []
        bucket = self.hour_prices.setdefault(close_time, {})
        bucket[event.symbol] = price
        if set(bucket) != {BTC, self.alt} or self.last_processed_hour == close_time:
            return []
        self.last_processed_hour = close_time
        current = {BTC: bucket[BTC], self.alt: bucket[self.alt]}
        self.hour_prices = {key: value for key, value in self.hour_prices.items() if key >= close_time}
        if self.previous_prices is None:
            self.previous_prices = current
            return []
        with localcontext(m102_decimal_context()):
            btc_return = current[BTC] / self.previous_prices[BTC] - Decimal(1)
            alt_return = current[self.alt] / self.previous_prices[self.alt] - Decimal(1)
            self.previous_prices = current
            self.returns.append((btc_return, alt_return))
            if len(self.returns) < self.lookback:
                return []
            btc_values = [item[0] for item in self.returns]
            alt_values = [item[1] for item in self.returns]
            btc_mean = sum(btc_values, Decimal(0)) / Decimal(len(btc_values))
            alt_mean = sum(alt_values, Decimal(0)) / Decimal(len(alt_values))
            denominator = sum(((item - btc_mean) ** 2 for item in btc_values), Decimal(0))
            if denominator == 0:
                return []
            beta = sum(
                ((btc_value - btc_mean) * (alt_value - alt_mean)
                 for btc_value, alt_value in zip(btc_values, alt_values, strict=True)),
                Decimal(0),
            ) / denominator
            beta = min(self.beta_max, max(self.beta_min, beta))
            residual = alt_return - beta * btc_return
            self.residuals.append(residual)
            if len(self.residuals) < self.lookback:
                return []
            mean = sum(self.residuals, Decimal(0)) / Decimal(len(self.residuals))
            variance = sum(((item - mean) ** 2 for item in self.residuals), Decimal(0)) / Decimal(len(self.residuals))
            if variance <= 0:
                return []
            z_score = (residual - mean) / variance.sqrt()

            pending = set(state.get("pending_instruments", ()))
            if pending:
                return []
            if self.active_side:
                expired = self.entered_at_ms is not None and close_time - self.entered_at_ms >= self.max_holding_ms
                if abs(z_score) < self.exit_z or expired:
                    self.active_side = 0
                    self.entered_at_ms = None
                    return [
                        TargetExposureIntent(self.alt, "perpetual_ohlcv", "0"),
                        TargetExposureIntent(BTC, "perpetual_ohlcv", "0"),
                    ]
                return []
            if z_score >= self.entry_z:
                self.active_side = -1
            elif z_score <= -self.entry_z:
                self.active_side = 1
            else:
                return []
            self.entered_at_ms = close_time
            return self._targets(self.active_side, beta)


def _variant(alt: str, hours: int) -> VariantDefinition:
    instruments = (f"perpetual_ohlcv:{BTC}", f"perpetual_ohlcv:{alt}")
    observable = (*instruments, f"funding_rates:{BTC}", f"funding_rates:{alt}")
    return VariantDefinition(
        variant_id=f"RAB1_{alt.removesuffix('USDT')}_BTC_{hours}H",
        required_streams=("perpetual_ohlcv", "funding_rates"),
        required_symbols=(BTC, alt),
        observable_inputs=observable,
        tradable_instruments=instruments,
        informational_streams=("funding_rates",),
        initial_research_nav="10000",
        max_gross_research_exposure="2000",
        max_net_research_exposure="2000",
        per_instrument_bounds={instrument: "2000" for instrument in instruments},
        fee_bps="5",
        slippage_bps="5",
        funding_accounting_applicable=True,
        strategy_parameters=MappingProxyType({
            "alt_symbol": alt,
            "beta_max": "3",
            "beta_min": "0.25",
            "entry_z": "2",
            "estimation_hours": hours,
            "exit_z": "0.5",
            "gross_research_exposure": "2000",
            "maximum_holding_hours": 24,
            "price_return": "SIMPLE_CLOSE_TO_CLOSE_DECIMAL",
            "residual_definition": "ALT_RETURN_MINUS_BETA_TIMES_BTC_RETURN",
        }),
    )


def family_definition() -> FamilyDefinition:
    variants = tuple(_variant(alt, hours) for alt in ALTS for hours in LOOKBACKS)
    return FamilyDefinition(FAMILY_ID, variants, lambda parameters: ResidualReversionAdapter(parameters))

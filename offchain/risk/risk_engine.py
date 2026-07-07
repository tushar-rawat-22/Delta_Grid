from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class TradeSimulation:
    gross_profit_wei: int
    gas_cost_wei: int
    flash_fee_wei: int
    slippage_cost_wei: int
    slippage_bps: int
    estimated_success_bps: int = 10_000

    @property
    def total_cost_wei(self) -> int:
        return self.gas_cost_wei + self.flash_fee_wei + self.slippage_cost_wei

    @property
    def net_profit_wei(self) -> int:
        return self.gross_profit_wei - self.total_cost_wei

    @property
    def gas_to_gross_bps(self) -> int:
        if self.gross_profit_wei <= 0:
            return 10_000

        return int((self.gas_cost_wei * 10_000) / self.gross_profit_wei)


@dataclass(frozen=True)
class RiskLimits:
    min_net_profit_wei: int = 1_000_000_000_000_000
    max_slippage_bps: int = 50
    max_gas_to_gross_bps: int = 3_000
    min_success_bps: int = 8_500
    min_score: int = 70


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    score: int
    net_profit_wei: int
    total_cost_wei: int
    reasons: List[str]


def evaluate_trade(
    trade: TradeSimulation,
    limits: RiskLimits = RiskLimits(),
) -> RiskDecision:
    score = 100
    reasons: List[str] = []

    if trade.gross_profit_wei <= 0:
        score -= 50
        reasons.append("gross profit must be positive")

    if trade.net_profit_wei < limits.min_net_profit_wei:
        score -= 35
        reasons.append("net profit below minimum threshold")

    if trade.total_cost_wei >= trade.gross_profit_wei:
        score -= 30
        reasons.append("total costs exceed or equal gross profit")

    if trade.slippage_bps > limits.max_slippage_bps:
        score -= 20
        reasons.append("slippage exceeds maximum allowed bps")

    if trade.gas_to_gross_bps > limits.max_gas_to_gross_bps:
        score -= 15
        reasons.append("gas cost too high relative to gross profit")

    if trade.estimated_success_bps < limits.min_success_bps:
        score -= 20
        reasons.append("estimated success probability too low")

    score = max(0, min(100, score))

    approved = len(reasons) == 0 and score >= limits.min_score

    return RiskDecision(
        approved=approved,
        score=score,
        net_profit_wei=trade.net_profit_wei,
        total_cost_wei=trade.total_cost_wei,
        reasons=reasons,
    )

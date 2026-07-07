// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import {DeltaGridRiskGuard} from "./DeltaGridRiskGuard.sol";

interface IERC20Minimal {
    function balanceOf(address account) external view returns (uint256);
}

contract DeltaGridExecutor is AccessControl, ReentrancyGuard {
    bytes32 public constant EXECUTOR_ADMIN_ROLE = keccak256("EXECUTOR_ADMIN_ROLE");
    bytes32 public constant BOT_ROLE = keccak256("BOT_ROLE");

    DeltaGridRiskGuard public immutable riskGuard;

    event SimulatedExecutionAccepted(
        address indexed bot,
        address indexed tokenIn,
        address indexed tokenOut,
        uint256 startingBalance,
        uint256 endingBalance,
        uint256 minProfit
    );

    constructor(address admin, address riskGuard_) {
        require(admin != address(0), "ZERO_ADMIN");
        require(riskGuard_ != address(0), "ZERO_RISK_GUARD");

        riskGuard = DeltaGridRiskGuard(riskGuard_);

        _grantRole(DEFAULT_ADMIN_ROLE, admin);
        _grantRole(EXECUTOR_ADMIN_ROLE, admin);
        _grantRole(BOT_ROLE, admin);
    }

    function simulatedExecutionCheck(
        address tokenIn,
        address tokenOut,
        address router,
        address oracle,
        uint256 expectedProfitWei,
        uint256 gasCostWei,
        uint256 startingBalance,
        uint256 endingBalance,
        uint256 minProfit
    ) external nonReentrant onlyRole(BOT_ROLE) returns (bool) {
        riskGuard.checkTrade(tokenIn, tokenOut, router, oracle, expectedProfitWei, gasCostWei);

        require(endingBalance >= startingBalance + minProfit, "FINAL_PROFIT_TOO_LOW");

        emit SimulatedExecutionAccepted(msg.sender, tokenIn, tokenOut, startingBalance, endingBalance, minProfit);

        return true;
    }
}

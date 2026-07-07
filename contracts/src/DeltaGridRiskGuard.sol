// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";
import {Pausable} from "@openzeppelin/contracts/utils/Pausable.sol";
import {AggregatorV3Interface} from "@chainlink/contracts/src/v0.8/shared/interfaces/AggregatorV3Interface.sol";
import {DeltaGridRegistry} from "./DeltaGridRegistry.sol";

contract DeltaGridRiskGuard is AccessControl, Pausable {
    bytes32 public constant RISK_ADMIN_ROLE = keccak256("RISK_ADMIN_ROLE");
    bytes32 public constant EXECUTOR_ROLE = keccak256("EXECUTOR_ROLE");

    DeltaGridRegistry public immutable registry;

    uint256 public minProfitWei;
    uint256 public maxOracleStalenessSeconds;

    event RiskApproved(
        address indexed executor,
        address indexed tokenIn,
        address indexed tokenOut,
        address oracle,
        uint256 expectedProfitWei,
        uint256 gasCostWei,
        uint256 minProfitWei
    );

    event MinProfitUpdated(uint256 oldValue, uint256 newValue);
    event MaxOracleStalenessUpdated(uint256 oldValue, uint256 newValue);

    constructor(address admin, address registry_, uint256 minProfitWei_, uint256 maxOracleStalenessSeconds_) {
        require(admin != address(0), "ZERO_ADMIN");
        require(registry_ != address(0), "ZERO_REGISTRY");

        registry = DeltaGridRegistry(registry_);
        minProfitWei = minProfitWei_;
        maxOracleStalenessSeconds = maxOracleStalenessSeconds_;

        _grantRole(DEFAULT_ADMIN_ROLE, admin);
        _grantRole(RISK_ADMIN_ROLE, admin);
        _grantRole(EXECUTOR_ROLE, admin);
    }

    function pause() external onlyRole(RISK_ADMIN_ROLE) {
        _pause();
    }

    function unpause() external onlyRole(RISK_ADMIN_ROLE) {
        _unpause();
    }

    function setMinProfitWei(uint256 newMinProfitWei) external onlyRole(RISK_ADMIN_ROLE) {
        uint256 old = minProfitWei;
        minProfitWei = newMinProfitWei;
        emit MinProfitUpdated(old, newMinProfitWei);
    }

    function setMaxOracleStalenessSeconds(uint256 newValue) external onlyRole(RISK_ADMIN_ROLE) {
        require(newValue > 0, "BAD_STALENESS");
        uint256 old = maxOracleStalenessSeconds;
        maxOracleStalenessSeconds = newValue;
        emit MaxOracleStalenessUpdated(old, newValue);
    }

    function checkOracleFreshness(address oracle) public view returns (bool) {
        require(registry.allowedOracles(oracle), "ORACLE_NOT_ALLOWED");

        (, int256 answer,, uint256 updatedAt,) = AggregatorV3Interface(oracle).latestRoundData();

        require(answer > 0, "BAD_ORACLE_PRICE");
        require(updatedAt > 0, "BAD_ORACLE_TIME");
        require(block.timestamp - updatedAt <= maxOracleStalenessSeconds, "STALE_ORACLE");

        return true;
    }

    function checkTrade(
        address tokenIn,
        address tokenOut,
        address router,
        address oracle,
        uint256 expectedProfitWei,
        uint256 gasCostWei
    ) external whenNotPaused onlyRole(EXECUTOR_ROLE) returns (bool) {
        require(registry.allowedTokens(tokenIn), "TOKEN_IN_NOT_ALLOWED");
        require(registry.allowedTokens(tokenOut), "TOKEN_OUT_NOT_ALLOWED");
        require(registry.allowedRouters(router), "ROUTER_NOT_ALLOWED");

        checkOracleFreshness(oracle);

        require(expectedProfitWei > gasCostWei, "NEGATIVE_AFTER_GAS");

        uint256 netProfit = expectedProfitWei - gasCostWei;
        require(netProfit >= minProfitWei, "BELOW_MIN_PROFIT");

        emit RiskApproved(msg.sender, tokenIn, tokenOut, oracle, expectedProfitWei, gasCostWei, minProfitWei);

        return true;
    }
}

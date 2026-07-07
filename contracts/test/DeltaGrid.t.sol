// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {DeltaGridRegistry} from "../src/DeltaGridRegistry.sol";
import {DeltaGridRiskGuard} from "../src/DeltaGridRiskGuard.sol";
import {DeltaGridExecutor} from "../src/DeltaGridExecutor.sol";
import {MockOracle} from "../src/MockOracle.sol";

contract DeltaGridTest is Test {
    DeltaGridRegistry registry;
    DeltaGridRiskGuard riskGuard;
    DeltaGridExecutor executor;
    MockOracle oracle;

    address admin = address(this);
    address tokenIn = address(0x1001);
    address tokenOut = address(0x1002);
    address router = address(0x2001);

    function setUp() public {
        registry = new DeltaGridRegistry(admin);
        oracle = new MockOracle(3000e8);

        registry.setToken(tokenIn, true);
        registry.setToken(tokenOut, true);
        registry.setRouter(router, true);
        registry.setOracle(address(oracle), true);

        riskGuard = new DeltaGridRiskGuard(admin, address(registry), 1 ether, 3600);

        executor = new DeltaGridExecutor(admin, address(riskGuard));

        riskGuard.grantRole(riskGuard.EXECUTOR_ROLE(), address(executor));
    }

    function testRiskGuardApprovesValidTrade() public {
        bool ok = riskGuard.checkTrade(tokenIn, tokenOut, router, address(oracle), 3 ether, 1 ether);

        assertTrue(ok);
    }

    function testRiskGuardRejectsBadToken() public {
        vm.expectRevert("TOKEN_IN_NOT_ALLOWED");

        riskGuard.checkTrade(address(0x9999), tokenOut, router, address(oracle), 3 ether, 1 ether);
    }

    function testRiskGuardRejectsNegativeAfterGas() public {
        vm.expectRevert("NEGATIVE_AFTER_GAS");

        riskGuard.checkTrade(tokenIn, tokenOut, router, address(oracle), 1 ether, 2 ether);
    }

    function testRiskGuardRejectsStaleOracle() public {
        vm.warp(10_000);

        oracle.setUpdatedAt(block.timestamp - 7200);

        vm.expectRevert("STALE_ORACLE");

        riskGuard.checkTrade(tokenIn, tokenOut, router, address(oracle), 3 ether, 1 ether);
    }

    function testExecutorAcceptsSafeSimulatedExecution() public {
        bool ok = executor.simulatedExecutionCheck(
            tokenIn, tokenOut, router, address(oracle), 3 ether, 1 ether, 10 ether, 12 ether, 1 ether
        );

        assertTrue(ok);
    }

    function testExecutorRejectsBadFinalProfit() public {
        vm.expectRevert("FINAL_PROFIT_TOO_LOW");

        executor.simulatedExecutionCheck(
            tokenIn, tokenOut, router, address(oracle), 3 ether, 1 ether, 10 ether, 10.5 ether, 1 ether
        );
    }
}

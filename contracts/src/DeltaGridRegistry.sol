// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";

contract DeltaGridRegistry is AccessControl {
    bytes32 public constant REGISTRY_ADMIN_ROLE = keccak256("REGISTRY_ADMIN_ROLE");

    mapping(address => bool) public allowedTokens;
    mapping(address => bool) public allowedRouters;
    mapping(address => bool) public allowedOracles;

    event TokenStatusUpdated(address indexed token, bool allowed);
    event RouterStatusUpdated(address indexed router, bool allowed);
    event OracleStatusUpdated(address indexed oracle, bool allowed);

    constructor(address admin) {
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
        _grantRole(REGISTRY_ADMIN_ROLE, admin);
    }

    function setToken(address token, bool allowed) external onlyRole(REGISTRY_ADMIN_ROLE) {
        require(token != address(0), "ZERO_TOKEN");
        allowedTokens[token] = allowed;
        emit TokenStatusUpdated(token, allowed);
    }

    function setRouter(address router, bool allowed) external onlyRole(REGISTRY_ADMIN_ROLE) {
        require(router != address(0), "ZERO_ROUTER");
        allowedRouters[router] = allowed;
        emit RouterStatusUpdated(router, allowed);
    }

    function setOracle(address oracle, bool allowed) external onlyRole(REGISTRY_ADMIN_ROLE) {
        require(oracle != address(0), "ZERO_ORACLE");
        allowedOracles[oracle] = allowed;
        emit OracleStatusUpdated(oracle, allowed);
    }
}

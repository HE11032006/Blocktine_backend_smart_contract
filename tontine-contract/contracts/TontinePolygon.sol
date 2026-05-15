// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

contract TontinePolygon is ReentrancyGuard {
    IERC20 public usdc;

    struct Group {
        uint256 amountPerMember;
        uint256 frequency;
        uint256 startTime;
        uint256 currentRound;
        address[] members;
        mapping(address => mapping(uint256 => bool)) hasPaid;
        bool isActive;
    }

    mapping(uint256 => Group) public groups;
    uint256 public nextGroupId;

    event GroupCreated(uint256 indexed groupId, uint256 amountPerMember, uint256 frequency);
    event DepositMade(uint256 indexed groupId, address indexed member, uint256 round);
    event WinnerDistributed(uint256 indexed groupId, address indexed winner, uint256 round, uint256 amount);

    constructor(address _usdcAddress) {
        usdc = IERC20(_usdcAddress);
    }

    function createGroup(
        uint256 _amountPerMember,
        uint256 _frequency,
        address[] calldata _members
    ) external returns (uint256 groupId) {
        require(_members.length >= 2, "Need at least 2 members");
        require(_amountPerMember > 0, "Amount must be > 0");
        require(_frequency > 0, "Frequency must be > 0");

        groupId = nextGroupId++;
        Group storage g = groups[groupId];
        g.amountPerMember = _amountPerMember;
        g.frequency = _frequency;
        g.startTime = block.timestamp;
        g.currentRound = 1;
        g.isActive = true;
        g.members = _members;

        emit GroupCreated(groupId, _amountPerMember, _frequency);
    }

    function deposit(uint256 _groupId) external nonReentrant {
        Group storage g = groups[_groupId];
        require(g.isActive, "Group not active");
        
        uint256 round = getCurrentRound(_groupId);
        require(round <= g.members.length, "Tontine finished");
        require(!g.hasPaid[msg.sender][round], "Already paid this round");

        require(usdc.transferFrom(msg.sender, address(this), g.amountPerMember), "USDC transfer failed");

        g.hasPaid[msg.sender][round] = true;
        emit DepositMade(_groupId, msg.sender, round);
    }

    function distribute(uint256 _groupId) external nonReentrant {
        Group storage g = groups[_groupId];
        require(g.isActive, "Group not active");
        
        uint256 round = getCurrentRound(_groupId);
        require(round <= g.members.length, "Tontine finished");

        for (uint256 i = 0; i < g.members.length; i++) {
            require(g.hasPaid[g.members[i]][round], "Not all members paid");
        }

        address winner = g.members[round - 1];
        uint256 totalAmount = g.amountPerMember * g.members.length;

        require(usdc.transfer(winner, totalAmount), "USDC transfer failed");

        for (uint256 i = 0; i < g.members.length; i++) {
            g.hasPaid[g.members[i]][round] = false;
        }
        g.currentRound++;

        emit WinnerDistributed(_groupId, winner, round, totalAmount);
    }

    function getCurrentRound(uint256 _groupId) public view returns (uint256) {
        Group storage g = groups[_groupId];
        if (!g.isActive) return 0;
        
        uint256 elapsed = block.timestamp - g.startTime;
        uint256 round = (elapsed / g.frequency) + 1;
        
        if (round > g.members.length) {
            round = g.members.length;
        }
        return round;
    }

    function hasMemberPaid(uint256 _groupId, address _member, uint256 _round) external view returns (bool) {
        return groups[_groupId].hasPaid[_member][_round];
    }

    function getGroupMembers(uint256 _groupId) external view returns (address[] memory) {
        return groups[_groupId].members;
    }

    function getMemberCount(uint256 _groupId) external view returns (uint256) {
        return groups[_groupId].members.length;
    }
}
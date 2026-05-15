// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

/**
 * @title ERC20Mock
 * @notice Token ERC20 factice pour les tests sur Polygon Amoy
 */
contract ERC20Mock is ERC20 {
    constructor() ERC20("Mock USDC", "mUSDC") {
        // Mint 1 million de tokens pour le déployeur
        _mint(msg.sender, 1_000_000 * 10 ** decimals());
    }

    function mint(address to, uint256 amount) external {
        _mint(to, amount);
    }
}

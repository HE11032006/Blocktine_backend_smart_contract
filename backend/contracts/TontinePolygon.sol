// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

/**
 * @title TontinePolygon
 * @notice Contrat de tontine sécurisé — Polygon Amoy
 * @dev Sécurités : ReentrancyGuard, nonce anti-replay par membre,
 *      deadline par tour, vérification solde ERC20 avant transfert.
 */
contract TontinePolygon is ReentrancyGuard, Ownable {

    IERC20 public immutable token;

    // ── Structures ────────────────────────────────────────────────────────────

    struct TontineGroup {
        address[] members;
        uint256 amountPerMember;      // en wei du token (ex: 6 décimales pour USDC)
        uint256 intervalSeconds;
        uint256 currentRound;
        bool active;

        // member => isMember
        mapping(address => bool) isMember;

        // member => nonce (nombre de dépôts effectués, incrémenté à chaque deposit)
        // Anti-replay : un deposit pour le round N exige nonce == N
        mapping(address => uint256) memberNonce;

        // round => member => hasPaid
        mapping(uint256 => mapping(address => bool)) hasPaid;

        // round => total collecté
        mapping(uint256 => uint256) roundBalance;

        // round => deadline (timestamp UNIX)
        mapping(uint256 => uint256) roundDeadline;

        // round => nombre de membres ayant payé
        mapping(uint256 => uint256) paidCount;
    }

    mapping(uint256 => TontineGroup) private groups;

    // ── Events ────────────────────────────────────────────────────────────────

    event GroupCreated(
        uint256 indexed groupId,
        address[] members,
        uint256 amountPerMember,
        uint256 intervalSeconds
    );

    event RoundOpened(
        uint256 indexed groupId,
        uint256 indexed round,
        uint256 deadline
    );

    event DepositMade(
        uint256 indexed groupId,
        address indexed member,
        uint256 indexed round,
        uint256 amount,
        uint256 memberNonce
    );

    event WinnerDistributed(
        uint256 indexed groupId,
        address indexed winner,
        uint256 indexed round,
        uint256 amount,
        bool allPaid  // true si tous les membres avaient payé
    );

    event MemberDefaulted(
        uint256 indexed groupId,
        address indexed member,
        uint256 indexed round
    );

    // ── Modifiers ─────────────────────────────────────────────────────────────

    modifier onlyGroupMember(uint256 groupId) {
        require(groups[groupId].isMember[msg.sender], "Non membre du groupe");
        _;
    }

    modifier groupExists(uint256 groupId) {
        require(groups[groupId].active, "Groupe inexistant ou inactif");
        _;
    }

    modifier roundOpen(uint256 groupId) {
        TontineGroup storage g = groups[groupId];
        uint256 round = g.currentRound;
        require(g.roundDeadline[round] > 0, "Tour non ouvert");
        require(block.timestamp <= g.roundDeadline[round], "Deadline du tour depassee");
        _;
    }

    // ── Constructor ───────────────────────────────────────────────────────────

    constructor(address tokenAddress) Ownable(msg.sender) {
        require(tokenAddress != address(0), "Token invalide");
        token = IERC20(tokenAddress);
    }

    // ── Admin : création groupe ───────────────────────────────────────────────

    /**
     * @notice Crée un groupe de tontine
     * @param groupId           ID unique (correspond à l'UUID PostgreSQL converti en uint256)
     * @param members           Adresses des membres (2–20)
     * @param amountPerMember   Montant en wei à verser par membre par tour
     * @param intervalSeconds   Durée entre deux tours (ex: 2592000 = 30 jours)
     * @param firstDeadline     Timestamp UNIX de la deadline du premier tour
     */
    function createGroup(
        uint256 groupId,
        address[] memory members,
        uint256 amountPerMember,
        uint256 intervalSeconds,
        uint256 firstDeadline
    ) external onlyOwner {
        require(!groups[groupId].active, "Groupe deja cree");
        require(members.length >= 2 && members.length <= 20, "2 a 20 membres requis");
        require(amountPerMember > 0, "Montant invalide");
        require(firstDeadline > block.timestamp, "Deadline dans le passe");
        require(intervalSeconds >= 3600, "Intervalle minimum 1 heure");

        // Vérifier pas d'adresses nulles ou dupliquées
        for (uint256 i = 0; i < members.length; i++) {
            require(members[i] != address(0), "Adresse membre invalide");
            for (uint256 j = i + 1; j < members.length; j++) {
                require(members[i] != members[j], "Membre duplique");
            }
        }

        TontineGroup storage g = groups[groupId];
        g.members = members;
        g.amountPerMember = amountPerMember;
        g.intervalSeconds = intervalSeconds;
        g.currentRound = 0;
        g.active = true;
        g.roundDeadline[0] = firstDeadline;

        for (uint256 i = 0; i < members.length; i++) {
            g.isMember[members[i]] = true;
            g.memberNonce[members[i]] = 0; // nonce initial = 0
        }

        emit GroupCreated(groupId, members, amountPerMember, intervalSeconds);
        emit RoundOpened(groupId, 0, firstDeadline);
    }

    // ── Dépôt ────────────────────────────────────────────────────────────────

    /**
     * @notice Dépose le montant pour le tour actuel
     * @dev Anti-replay : vérifie que memberNonce == currentRound
     *      Le membre doit avoir appelé token.approve(contractAddress, amount) avant
     * @param groupId   ID du groupe
     * @param expectedRound  Round attendu par le client (protection replay cross-round)
     */
    function deposit(uint256 groupId, uint256 expectedRound)
        external
        nonReentrant
        groupExists(groupId)
        onlyGroupMember(groupId)
        roundOpen(groupId)
    {
        TontineGroup storage g = groups[groupId];
        uint256 round = g.currentRound;

        // Anti-replay : le round demandé doit correspondre au round actuel
        require(expectedRound == round, "Round incorrect (replay detecte)");

        // Anti-replay : le nonce du membre doit correspondre au round actuel
        require(g.memberNonce[msg.sender] == round, "Nonce invalide (depot deja effectue)");

        // Double-dépôt explicite
        require(!g.hasPaid[round][msg.sender], "Deja paye pour ce tour");

        // Vérifier le solde avant transfert (protection overflow)
        uint256 balanceBefore = token.balanceOf(address(this));
        require(
            token.balanceOf(msg.sender) >= g.amountPerMember,
            "Solde insuffisant"
        );
        require(
            token.allowance(msg.sender, address(this)) >= g.amountPerMember,
            "Approbation insuffisante (approve requis)"
        );

        // Transfert
        require(
            token.transferFrom(msg.sender, address(this), g.amountPerMember),
            "Transfert token echoue"
        );

        // Vérifier que le contrat a bien reçu le montant exact (protection fee-on-transfer tokens)
        uint256 received = token.balanceOf(address(this)) - balanceBefore;
        require(received == g.amountPerMember, "Montant recu incorrect");

        // Mettre à jour l'état APRÈS le transfert
        g.hasPaid[round][msg.sender] = true;
        g.roundBalance[round] += received;
        g.paidCount[round] += 1;

        // Incrémenter le nonce anti-replay du membre
        g.memberNonce[msg.sender] += 1;

        emit DepositMade(groupId, msg.sender, round, received, g.memberNonce[msg.sender] - 1);
    }

    // ── Distribution ─────────────────────────────────────────────────────────

    /**
     * @notice Distribue la cagnotte au gagnant du tour
     * @param groupId       ID du groupe
     * @param winner        Adresse du gagnant (déterminée off-chain)
     * @param forcePartial  Si true, distribue même si tous n'ont pas payé (admin override)
     *                      Les membres défaillants sont loggés via MemberDefaulted
     */
    function distribute(
        uint256 groupId,
        address winner,
        bool forcePartial
    )
        external
        nonReentrant
        onlyOwner
        groupExists(groupId)
    {
        TontineGroup storage g = groups[groupId];
        uint256 round = g.currentRound;

        require(g.isMember[winner], "Le gagnant n'est pas membre");

        uint256 balance = g.roundBalance[round];
        require(balance > 0, "Aucun fond a distribuer");

        bool allPaid = (g.paidCount[round] == g.members.length);

        // Si pas tous payés et pas de force → revert
        if (!allPaid && !forcePartial) {
            revert("Tous les membres n'ont pas paye (utiliser forcePartial pour override)");
        }

        // Logger les membres défaillants
        if (!allPaid) {
            for (uint256 i = 0; i < g.members.length; i++) {
                if (!g.hasPaid[round][g.members[i]]) {
                    emit MemberDefaulted(groupId, g.members[i], round);
                }
            }
        }

        // Réinitialiser AVANT le transfert (protection réentrance)
        g.roundBalance[round] = 0;
        uint256 nextRound = round + 1;
        g.currentRound = nextRound;

        // Ouvrir le prochain tour avec sa deadline
        uint256 nextDeadline = block.timestamp + g.intervalSeconds;
        g.roundDeadline[nextRound] = nextDeadline;

        // Transfert au gagnant
        require(token.transfer(winner, balance), "Transfert gagnant echoue");

        emit WinnerDistributed(groupId, winner, round, balance, allPaid);
        emit RoundOpened(groupId, nextRound, nextDeadline);
    }

    // ── Vues ─────────────────────────────────────────────────────────────────

    function getCurrentRound(uint256 groupId) external view returns (uint256) {
        return groups[groupId].currentRound;
    }

    function getRoundBalance(uint256 groupId, uint256 round)
        external view returns (uint256)
    {
        return groups[groupId].roundBalance[round];
    }

    function getRoundDeadline(uint256 groupId, uint256 round)
        external view returns (uint256)
    {
        return groups[groupId].roundDeadline[round];
    }

    function hasMemberPaid(uint256 groupId, uint256 round, address member)
        external view returns (bool)
    {
        return groups[groupId].hasPaid[round][member];
    }

    function getMemberNonce(uint256 groupId, address member)
        external view returns (uint256)
    {
        return groups[groupId].memberNonce[member];
    }

    function getPaidCount(uint256 groupId, uint256 round)
        external view returns (uint256)
    {
        return groups[groupId].paidCount[round];
    }

    function getMembers(uint256 groupId)
        external view returns (address[] memory)
    {
        return groups[groupId].members;
    }

    function isRoundOpen(uint256 groupId)
        external view returns (bool)
    {
        TontineGroup storage g = groups[groupId];
        uint256 round = g.currentRound;
        return (
            g.roundDeadline[round] > 0 &&
            block.timestamp <= g.roundDeadline[round]
        );
    }
}

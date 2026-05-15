"""
Tests unitaires — Sécurité du smart contract (simulés côté Python)
Ces tests vérifient que BlockchainService appelle le contrat avec les bons arguments
et que la logique anti-replay est correcte.

Pour les tests Solidity (Hardhat) : voir contracts/test/TontinePolygon.test.js
"""
import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from app.services.blockchain_service import BlockchainService


@pytest.fixture
def mock_blockchain():
    """BlockchainService avec Web3 entièrement mocké."""
    with patch("app.services.blockchain_service.Web3") as MockWeb3:
        mock_w3 = MagicMock()
        MockWeb3.return_value = mock_w3
        MockWeb3.to_checksum_address.side_effect = lambda x: x.lower()
        MockWeb3.HTTPProvider.return_value = MagicMock()

        mock_w3.is_connected.return_value = True
        mock_w3.eth.get_transaction_count.return_value = 1
        mock_w3.eth.gas_price = 30_000_000_000
        mock_w3.eth.send_raw_transaction.return_value = b"\xab\xcd" * 16
        mock_w3.to_hex.return_value = "0xabcd" * 8

        # Mock du compte
        mock_account = MagicMock()
        mock_account.address = "0xdeadbeef"
        mock_w3.eth.account.from_key.return_value = mock_account
        mock_w3.eth.account.sign_transaction.return_value = MagicMock(
            raw_transaction=b"\x00" * 32
        )

        with patch("app.services.blockchain_service.settings") as mock_settings:
            mock_settings.polygon_rpc_url = "https://rpc-amoy.polygon.technology"
            mock_settings.private_key = "0x" + "a" * 64
            mock_settings.contract_address = "0x" + "b" * 40

            service = BlockchainService.__new__(BlockchainService)
            service.w3 = mock_w3
            service.account = mock_account
            service.contract = MagicMock()
            service.token_contract = MagicMock()

            yield service


# ── Test 1 : deposit() passe le expectedRound — anti-replay ───────────────────
def test_deposit_passes_expected_round(mock_blockchain):
    """Le service doit passer expectedRound au contrat pour la protection anti-replay."""
    mock_fn = MagicMock()
    mock_blockchain.contract.functions.deposit.return_value = mock_fn
    mock_fn.build_transaction.return_value = {"gas": 400_000}

    mock_blockchain.deposit(group_id=1, expected_round=3)

    mock_blockchain.contract.functions.deposit.assert_called_once_with(1, 3)


# ── Test 2 : deposit() round incorrect → simuler le revert contrat ────────────
def test_deposit_wrong_round_reverts(mock_blockchain):
    """Si le contrat reverte (nonce invalide), le service doit propager l'exception."""
    mock_blockchain.contract.functions.deposit.return_value.build_transaction.side_effect = (
        Exception("execution reverted: Round incorrect (replay detecte)")
    )

    with pytest.raises(Exception, match="replay detecte"):
        mock_blockchain.deposit(group_id=1, expected_round=999)


# ── Test 3 : distribute() avec forcePartial=False par défaut ──────────────────
def test_distribute_default_no_force_partial(mock_blockchain):
    """Par défaut, distribute() ne force pas la distribution partielle."""
    mock_fn = MagicMock()
    mock_blockchain.contract.functions.distribute.return_value = mock_fn
    mock_fn.build_transaction.return_value = {"gas": 400_000}

    winner = "0x" + "c" * 40
    mock_blockchain.distribute(group_id=1, winner_address=winner)

    # forcePartial doit être False
    mock_blockchain.contract.functions.distribute.assert_called_once_with(
        1, winner.lower(), False
    )


# ── Test 4 : distribute() admin force partiel ─────────────────────────────────
def test_distribute_force_partial(mock_blockchain):
    """L'admin peut forcer la distribution même si tous n'ont pas payé."""
    mock_fn = MagicMock()
    mock_blockchain.contract.functions.distribute.return_value = mock_fn
    mock_fn.build_transaction.return_value = {"gas": 400_000}

    winner = "0x" + "d" * 40
    mock_blockchain.distribute(group_id=2, winner_address=winner, force_partial=True)

    mock_blockchain.contract.functions.distribute.assert_called_once_with(
        2, winner.lower(), True
    )


# ── Test 5 : get_balance_usdc lit bien l'ERC20, pas le MATIC natif ────────────
def test_get_balance_usdc_uses_erc20(mock_blockchain):
    """La balance doit venir du token ERC20, pas du solde natif."""
    mock_blockchain.token_contract.functions.balanceOf.return_value.call.return_value = (
        5_000_000  # 5 USDC en 6 décimales
    )
    mock_blockchain.token_contract.functions.decimals.return_value.call.return_value = 6

    balance = mock_blockchain.get_balance_usdc("0x" + "e" * 40)

    assert balance == "5.0"
    mock_blockchain.token_contract.functions.balanceOf.assert_called_once()
    # S'assurer que w3.eth.get_balance (MATIC) n'a PAS été appelé
    mock_blockchain.w3.eth.get_balance.assert_not_called()


# ── Test 6 : token_contract non initialisé → RuntimeError clair ───────────────
def test_get_balance_without_token_contract_raises(mock_blockchain):
    """Sans token_contract initialisé, une erreur claire doit être levée."""
    mock_blockchain.token_contract = None

    with pytest.raises(RuntimeError, match="Token contract non initialisé"):
        mock_blockchain.get_balance_usdc("0x" + "f" * 40)


# ── Test 7 : get_member_nonce retourne la valeur on-chain ─────────────────────
def test_get_member_nonce(mock_blockchain):
    mock_blockchain.contract.functions.getMemberNonce.return_value.call.return_value = 3

    nonce = mock_blockchain.get_member_nonce(group_id=1, member_address="0x" + "a" * 40)

    assert nonce == 3
    mock_blockchain.contract.functions.getMemberNonce.assert_called_once()


# ── Test 8 : createGroup valide les paramètres avant envoi ────────────────────
def test_create_group_builds_correct_tx(mock_blockchain):
    mock_fn = MagicMock()
    mock_blockchain.contract.functions.createGroup.return_value = mock_fn
    mock_fn.build_transaction.return_value = {"gas": 400_000}

    members = ["0x" + str(i) * 40 for i in range(1, 4)]
    mock_blockchain.create_group_on_chain(
        group_id=42,
        member_addresses=members,
        amount_usdc_wei=5_000_000,
        interval_seconds=2_592_000,
        first_deadline=9_999_999_999,
    )

    mock_blockchain.contract.functions.createGroup.assert_called_once_with(
        42,
        [m.lower() for m in members],
        5_000_000,
        2_592_000,
        9_999_999_999,
    )

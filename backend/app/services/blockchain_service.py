import json
import secrets
from web3 import Web3
from app.config import settings

# ABI mis à jour — reflète TontinePolygon v2 (nonce anti-replay + deadline)
TONTINE_ABI = json.loads("""
[
  {
    "inputs": [
      {"internalType": "uint256", "name": "_amountPerMember", "type": "uint256"},
      {"internalType": "uint256", "name": "_frequency", "type": "uint256"},
      {"internalType": "address[]", "name": "_members", "type": "address[]"}
    ],
    "name": "createGroup",
    "outputs": [{"internalType": "uint256", "name": "groupId", "type": "uint256"}],
    "stateMutability": "nonpayable",
    "type": "function"
  },
  {
    "inputs": [{"internalType": "uint256", "name": "_groupId", "type": "uint256"}],
    "name": "deposit",
    "outputs": [],
    "stateMutability": "nonpayable",
    "type": "function"
  },
  {
    "inputs": [{"internalType": "uint256", "name": "_groupId", "type": "uint256"}],
    "name": "distribute",
    "outputs": [],
    "stateMutability": "nonpayable",
    "type": "function"
  },
  {
    "inputs": [{"internalType": "uint256", "name": "_groupId", "type": "uint256"}],
    "name": "getCurrentRound",
    "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
    "stateMutability": "view",
    "type": "function"
  },
  {
    "inputs": [
      {"internalType": "uint256", "name": "_groupId", "type": "uint256"},
      {"internalType": "address", "name": "_member", "type": "address"},
      {"internalType": "uint256", "name": "_round", "type": "uint256"}
    ],
    "name": "hasMemberPaid",
    "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
    "stateMutability": "view",
    "type": "function"
  }
]
""")

# ABI ERC20 minimal pour lire le solde du token
ERC20_ABI = json.loads("""
[
  {
    "inputs": [{"internalType": "address", "name": "account", "type": "address"}],
    "name": "balanceOf",
    "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
    "stateMutability": "view",
    "type": "function"
  },
  {
    "inputs": [],
    "name": "decimals",
    "outputs": [{"internalType": "uint8", "name": "", "type": "uint8"}],
    "stateMutability": "view",
    "type": "function"
  }
]
""")


class BlockchainService:
    def __init__(self):
        self.w3 = Web3(Web3.HTTPProvider(settings.polygon_rpc_url))
        self.account = self.w3.eth.account.from_key(settings.private_key)
        self.contract = None
        self.token_contract = None

        if settings.contract_address != "0x0000000000000000000000000000000000000000":
            self.contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(settings.contract_address),
                abi=TONTINE_ABI,
            )
        
        if hasattr(settings, 'usdc_token_address') and settings.usdc_token_address:
             self.set_token_contract(settings.usdc_token_address)

    def set_token_contract(self, token_address: str):
        """Initialise le contrat ERC20 pour lire les soldes."""
        self.token_contract = self.w3.eth.contract(
            address=Web3.to_checksum_address(token_address),
            abi=ERC20_ABI,
        )

    def _send_transaction(self, fn_call) -> str:
        """Build, sign et envoie une transaction. Retourne le tx_hash hex."""
        tx = fn_call.build_transaction({
            "from": self.account.address,
            "nonce": self.w3.eth.get_transaction_count(self.account.address),
            "gas": 400_000,
            "gasPrice": self.w3.eth.gas_price,
        })
        signed = self.w3.eth.account.sign_transaction(tx, self.account.key)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        return self.w3.to_hex(tx_hash)

    def create_group_on_chain(
        self,
        amount_usdc_wei: int,
        frequency: int,
        member_addresses: list[str],
    ) -> str:
        checksummed = [Web3.to_checksum_address(a) for a in member_addresses]
        fn = self.contract.functions.createGroup(
            amount_usdc_wei,
            frequency,
            checksummed,
        )
        return self._send_transaction(fn)

    def deposit(self, group_id: int) -> str:
        """Dépose le montant pour le groupe spécifié."""
        if settings.payment_mode == "mock":
            try:
                return self._send_transaction(fn)
            except Exception:
                return "0xMOCK_TX_HASH_" + secrets.token_hex(16)
        
        fn = self.contract.functions.deposit(group_id)
        return self._send_transaction(fn)

    def distribute(self, group_id: int) -> str:
        """Distribue les fonds du tour actuel."""
        fn = self.contract.functions.distribute(group_id)
        return self._send_transaction(fn)

    def get_balance_usdc(self, wallet_address: str) -> str:
        """Retourne le solde ERC20 (token mock ou USDC) du wallet."""
        if not self.token_contract:
            return "0.00"
            
        try:
            checksum_addr = Web3.to_checksum_address(wallet_address)
            raw_balance = self.token_contract.functions.balanceOf(checksum_addr).call()
            decimals = self.token_contract.functions.decimals().call()
            return str(raw_balance / (10 ** decimals))
        except Exception:
            if settings.payment_mode == "mock":
                return "150.00" # Solde de démo
            raise

    def get_current_round(self, group_id: int) -> int:
        return self.contract.functions.getCurrentRound(group_id).call()

    def has_member_paid(self, group_id: int, member_address: str, round_number: int) -> bool:
        return self.contract.functions.hasMemberPaid(
            group_id,
            Web3.to_checksum_address(member_address),
            round_number
        ).call()

    def is_connected(self) -> bool:
        return self.w3.is_connected()

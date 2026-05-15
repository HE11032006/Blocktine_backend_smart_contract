import sys
import os
from pathlib import Path

# Ajouter le répertoire parent au path pour importer 'app'
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.services.blockchain_service import BlockchainService
from app.config import settings

def test_connection():
    print("--- Test de Connexion Blockchain ---")
    bc = BlockchainService()
    connected = bc.is_connected()
    print(f"Connecté à Polygon Amoy : {'✅' if connected else '❌'}")
    
    if connected:
        print(f"Wallet address: {bc.account.address}")
        try:
            balance = bc.w3.eth.get_balance(bc.account.address)
            print(f"Solde MATIC : {bc.w3.from_wei(balance, 'ether')} MATIC")
        except Exception as e:
            print(f"Erreur lors de la lecture du solde MATIC : {e}")

def test_contract_read():
    print("\n--- Test de Lecture du Contrat ---")
    bc = BlockchainService()
    if not bc.contract:
        print("❌ Contrat non configuré (CONTRACT_ADDRESS est à zéro)")
        return
    
    try:
        # On essaie une fonction view simple, par exemple getMembers pour le groupe 1
        # (Même si le groupe n'existe pas, ça devrait retourner une liste vide ou une erreur propre)
        members = bc.contract.functions.getMembers(1).call()
        print(f"Membres du groupe 1 : {members}")
        print("✅ Lecture du contrat réussie")
    except Exception as e:
        print(f"❌ Erreur lecture contrat : {e}")

if __name__ == "__main__":
    test_connection()
    test_contract_read()

# Tontine-Flow — Backend

Backend FastAPI pour la gestion de tontines sécurisées sur Polygon Amoy.

## Stack
- **FastAPI** + SQLAlchemy (sync) + psycopg2
- **Supabase Auth** (OTP SMS)
- **Alembic** (migrations versionnées)
- **Flutterwave** (Mobile Money MTN/Moov Bénin)
- **Web3.py** + Polygon Amoy (smart contract Solidity)
- **Render** (déploiement)

---

## Installation locale

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Remplir les variables dans .env
```

## Migrations

```bash
# Initialiser Alembic (déjà fait)
alembic upgrade head

# Créer une nouvelle migration après modif d'un modèle
alembic revision --autogenerate -m "description"
alembic upgrade head
```

## Lancer le serveur

```bash
uvicorn app.main:app --reload
# API disponible sur http://localhost:8000
# Docs : http://localhost:8000/docs
```

## Tests

```bash
pytest tests/ -v
```

---

## Déploiement Smart Contract (Polygon Amoy)

### Prérequis
```bash
npm install -g hardhat
npm install @openzeppelin/contracts
```

### Déployer ERC20Mock + TontinePolygon
```bash
# Dans un projet Hardhat séparé, copier les .sol
# Configurer hardhat.config.js avec Polygon Amoy :
# networks: { amoy: { url: "https://rpc-amoy.polygon.technology", accounts: [PRIVATE_KEY] } }

npx hardhat run scripts/deploy.js --network amoy
```

Script `scripts/deploy.js` :
```js
async function main() {
  const Token = await ethers.getContractFactory("ERC20Mock");
  const token = await Token.deploy();
  await token.waitForDeployment();
  console.log("ERC20Mock deployed:", await token.getAddress());

  const Tontine = await ethers.getContractFactory("TontinePolygon");
  const tontine = await Tontine.deploy(await token.getAddress());
  await tontine.waitForDeployment();
  console.log("TontinePolygon deployed:", await tontine.getAddress());
}
main().catch(console.error);
```

Copier `CONTRACT_ADDRESS` dans `.env`.

---

## Déploiement Render

```bash
# Pusher le code sur GitHub
git push origin main

# Sur render.com :
# 1. New Web Service → connecter le repo
# 2. Root directory : backend/
# 3. Render lit render.yaml automatiquement
# 4. Ajouter les secrets dans Environment Variables
```

---

## Initialisation Supabase

1. Créer un projet sur supabase.com
2. Activer **Phone Auth** dans Authentication > Providers
3. Configurer un provider SMS (Twilio recommandé)
4. Récupérer : `SUPABASE_URL`, `SUPABASE_KEY`, `SUPABASE_JWT_SECRET` (Settings > API)

---

## Variables d'environnement requises

| Variable | Description |
|---|---|
| `DATABASE_URL` | PostgreSQL Supabase |
| `SUPABASE_URL` | URL projet Supabase |
| `SUPABASE_KEY` | Clé anon Supabase |
| `SUPABASE_JWT_SECRET` | Secret JWT Supabase |
| `FLUTTERWAVE_PUBLIC_KEY` | Clé publique Flutterwave |
| `FLUTTERWAVE_SECRET_KEY` | Clé secrète Flutterwave |
| `FLUTTERWAVE_WEBHOOK_SECRET` | Secret webhook Flutterwave |
| `POLYGON_RPC_URL` | RPC Polygon Amoy |
| `PRIVATE_KEY` | Clé privée wallet déployeur |
| `CONTRACT_ADDRESS` | Adresse du contrat déployé |

---

## Architecture des flux

```
Mobile Money (MTN/Moov)
    ↓ Flutterwave
POST /payment/initiate → crée Payment(pending)
    ↓ webhook
POST /webhook/flutterwave → confirme Payment → dépôt blockchain
    ↓ distribute (admin ou automatique)
POST /admin/skip_round (si litige) ou blockchain.distribute()
    ↓
Gagnant reçoit FCFA sur son MoMo
```

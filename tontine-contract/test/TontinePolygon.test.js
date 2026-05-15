const { expect } = require("chai");
const { ethers } = require("hardhat");
const { time } = require("@nomicfoundation/hardhat-network-helpers");

describe("TontinePolygon — Sécurité", function () {
  let token, tontine;
  let owner, member1, member2, member3, stranger;
  const AMOUNT = ethers.parseUnits("100", 6); // 100 USDC mock (6 décimales)
  const INTERVAL = 30 * 24 * 3600; // 30 jours
  const GROUP_ID = 1;

  beforeEach(async function () {
    [owner, member1, member2, member3, stranger] = await ethers.getSigners();

    const Token = await ethers.getContractFactory("ERC20Mock");
    token = await Token.deploy();

    const Tontine = await ethers.getContractFactory("TontinePolygon");
    tontine = await Tontine.deploy(await token.getAddress());

    // Distribuer des tokens aux membres
    for (const m of [member1, member2, member3]) {
      await token.mint(m.address, ethers.parseUnits("10000", 6));
      await token.connect(m).approve(await tontine.getAddress(), ethers.MaxUint256);
    }

    // Créer un groupe avec deadline dans 7 jours
    const firstDeadline = (await time.latest()) + 7 * 24 * 3600;
    await tontine.createGroup(
      GROUP_ID,
      [member1.address, member2.address, member3.address],
      AMOUNT,
      INTERVAL,
      firstDeadline
    );
  });

  // ── Test 1 : Dépôt normal ─────────────────────────────────────────────────
  it("Accepte un dépôt valide", async function () {
    await expect(tontine.connect(member1).deposit(GROUP_ID, 0))
      .to.emit(tontine, "DepositMade")
      .withArgs(GROUP_ID, member1.address, 0, AMOUNT, 0);
  });

  // ── Test 2 : Anti-replay — double dépôt même tour ─────────────────────────
  it("Rejette un double dépôt sur le même tour", async function () {
    await tontine.connect(member1).deposit(GROUP_ID, 0);
    await expect(
      tontine.connect(member1).deposit(GROUP_ID, 0)
    ).to.be.revertedWith("Nonce invalide (depot deja effectue)");
  });

  // ── Test 3 : Anti-replay — expectedRound incorrect ────────────────────────
  it("Rejette un dépôt avec mauvais expectedRound", async function () {
    await expect(
      tontine.connect(member1).deposit(GROUP_ID, 999)
    ).to.be.revertedWith("Round incorrect (replay detecte)");
  });

  // ── Test 4 : Non-membre ne peut pas déposer ───────────────────────────────
  it("Rejette le dépôt d'un non-membre", async function () {
    await token.mint(stranger.address, ethers.parseUnits("1000", 6));
    await token.connect(stranger).approve(await tontine.getAddress(), ethers.MaxUint256);
    await expect(
      tontine.connect(stranger).deposit(GROUP_ID, 0)
    ).to.be.revertedWith("Non membre du groupe");
  });

  // ── Test 5 : Deadline dépassée → dépôt refusé ────────────────────────────
  it("Rejette un dépôt après la deadline", async function () {
    await time.increase(8 * 24 * 3600); // +8 jours
    await expect(
      tontine.connect(member1).deposit(GROUP_ID, 0)
    ).to.be.revertedWith("Deadline du tour depassee");
  });

  // ── Test 6 : Distribution sans tous les paiements — sans force → revert ───
  it("Bloque la distribution si tous n'ont pas payé (sans forcePartial)", async function () {
    await tontine.connect(member1).deposit(GROUP_ID, 0);
    // member2 et member3 n'ont pas payé
    await expect(
      tontine.distribute(GROUP_ID, member1.address, false)
    ).to.be.revertedWith("Tous les membres n'ont pas paye (utiliser forcePartial pour override)");
  });

  // ── Test 7 : forcePartial — distribue même incomplet ─────────────────────
  it("Distribue avec forcePartial même si incomplet, émet MemberDefaulted", async function () {
    await tontine.connect(member1).deposit(GROUP_ID, 0);
    // Seul member1 paie

    await expect(tontine.distribute(GROUP_ID, member1.address, true))
      .to.emit(tontine, "MemberDefaulted").withArgs(GROUP_ID, member2.address, 0)
      .and.to.emit(tontine, "MemberDefaulted").withArgs(GROUP_ID, member3.address, 0)
      .and.to.emit(tontine, "WinnerDistributed");

    // Le gagnant reçoit seulement ce qui a été déposé
    const balance = await token.balanceOf(member1.address);
    expect(balance).to.be.gte(ethers.parseUnits("10000", 6)); // récupère sa mise au moins
  });

  // ── Test 8 : Distribution complète — tous ont payé ────────────────────────
  it("Distribue correctement quand tous ont payé", async function () {
    await tontine.connect(member1).deposit(GROUP_ID, 0);
    await tontine.connect(member2).deposit(GROUP_ID, 0);
    await tontine.connect(member3).deposit(GROUP_ID, 0);

    const balanceBefore = await token.balanceOf(member2.address);
    await tontine.distribute(GROUP_ID, member2.address, false);
    const balanceAfter = await token.balanceOf(member2.address);

    expect(balanceAfter - balanceBefore).to.equal(AMOUNT * 3n);
  });

  // ── Test 9 : Nonce incrémenté après dépôt ─────────────────────────────────
  it("Incrémente le nonce du membre après dépôt", async function () {
    expect(await tontine.getMemberNonce(GROUP_ID, member1.address)).to.equal(0);
    await tontine.connect(member1).deposit(GROUP_ID, 0);
    expect(await tontine.getMemberNonce(GROUP_ID, member1.address)).to.equal(1);
  });

  // ── Test 10 : Prochain tour ouvert après distribution ─────────────────────
  it("Ouvre automatiquement le tour suivant après distribution", async function () {
    await tontine.connect(member1).deposit(GROUP_ID, 0);
    await tontine.connect(member2).deposit(GROUP_ID, 0);
    await tontine.connect(member3).deposit(GROUP_ID, 0);

    await expect(tontine.distribute(GROUP_ID, member1.address, false))
      .to.emit(tontine, "RoundOpened");

    expect(await tontine.getCurrentRound(GROUP_ID)).to.equal(1);
    expect(await tontine.isRoundOpen(GROUP_ID)).to.equal(true);
  });

  // ── Test 11 : Seul owner peut distribute ──────────────────────────────────
  it("Rejette distribute() si appelé par un non-owner", async function () {
    await tontine.connect(member1).deposit(GROUP_ID, 0);
    await tontine.connect(member2).deposit(GROUP_ID, 0);
    await tontine.connect(member3).deposit(GROUP_ID, 0);

    await expect(
      tontine.connect(member1).distribute(GROUP_ID, member1.address, false)
    ).to.be.revertedWithCustomError(tontine, "OwnableUnauthorizedAccount");
  });

  // ── Test 12 : Solde du contrat à zéro après distribution ──────────────────
  it("Le contrat ne retient aucun fond après distribution complète", async function () {
    await tontine.connect(member1).deposit(GROUP_ID, 0);
    await tontine.connect(member2).deposit(GROUP_ID, 0);
    await tontine.connect(member3).deposit(GROUP_ID, 0);

    await tontine.distribute(GROUP_ID, member3.address, false);

    const contractBalance = await token.balanceOf(await tontine.getAddress());
    expect(contractBalance).to.equal(0);
  });
});

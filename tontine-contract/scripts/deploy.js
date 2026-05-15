const hre = require("hardhat");

async function main() {
  const USDC_ADDRESS = "0x41e94eb019c0762f9bfcf9fb1e587a5bf67d2976";

  console.log("Déploiement sur Polygon Amoy...");
  console.log("USDC Token:", USDC_ADDRESS);

  const TontinePolygon = await hre.ethers.getContractFactory("TontinePolygon");
  const tontine = await TontinePolygon.deploy(USDC_ADDRESS);

  await tontine.waitForDeployment();

  const contractAddress = await tontine.getAddress();
  console.log("\n✅ CONTRAT DÉPLOYÉ !");
  console.log("📝 Adresse :", contractAddress);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});